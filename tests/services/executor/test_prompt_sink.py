"""Tests for PromptSink protocol and TerminalPromptSink."""
from __future__ import annotations

import builtins
import io

import pytest

from app.services.executor.prompt_sink import (
    PermissionOption,
    PromptSink,
    TerminalPromptSink,
)


class TestTerminalPromptSink:
    async def test_display_writes_to_stream(self) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.display("hello world")
        assert stream.getvalue() == "hello world"

    async def test_display_passthrough_no_auto_newline(self) -> None:
        """Streaming chunks must not be line-wrapped.

        Agent output arrives as token-sized fragments; the sink must
        concatenate them verbatim so the terminal renders agent
        formatting exactly as emitted.
        """
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        for chunk in ("What", " is", " your", " name", "?"):
            await sink.display(chunk)
        assert stream.getvalue() == "What is your name?"

    async def test_display_preserves_agent_newlines(self) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.display("line one\n")
        await sink.display("line two\n")
        assert stream.getvalue() == "line one\nline two\n"

    async def test_request_input_reads_stdin_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "175 cm")
        answer = await sink.request_input("height?")
        assert answer == "175 cm"
        assert "height?" in stream.getvalue()

    async def test_request_input_inserts_visual_separator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User must see a clear break between streamed agent output and
        the turn-over prompt; otherwise the prompt gets glued onto the last
        agent token. The styled "you" rule lives on its own line after a
        compensating newline.
        """
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.display("agent finished mid-sentence")
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "ok")
        await sink.request_input("reply?")
        rendered = stream.getvalue()
        # The streamed agent text gets its own newline before the rule.
        assert "agent finished mid-sentence\n" in rendered
        # The styled "you" rule renders, followed by the prompt label.
        assert "you" in rendered
        assert "reply?" in rendered
        # The rule is not glued to the streamed text — its first glyph
        # (the 👤 emoji) is on a new line.
        before_rule = rendered.split("👤")[0]
        assert before_rule.endswith("\n")

    async def test_request_input_echoes_piped_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Piped stdin doesn't echo keystrokes — the sink must echo the
        consumed line back so scripted transcripts read like a real
        terminal session."""
        import sys as _sys
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "scripted reply")
        monkeypatch.setattr(_sys.stdin, "isatty", lambda: False)
        await sink.request_input("reply?")
        rendered = stream.getvalue()
        assert "scripted reply" in rendered
        assert "you" in rendered  # styled rule label

    async def test_request_input_does_not_double_echo_on_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the user is actually typing, the terminal already echoes
        keystrokes — we must not write the answer back ourselves."""
        import sys as _sys
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "typed live")
        monkeypatch.setattr(_sys.stdin, "isatty", lambda: True)
        await sink.request_input("reply?")
        # The TTY branch must NOT print the answer; only the prompt label.
        assert "typed live" not in stream.getvalue()

    async def test_start_agent_turn_renders_styled_rule(self) -> None:
        """The agent-turn marker must be a horizontal rule with the
        'agent' label so the user can see when the agent starts speaking."""
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.start_agent_turn()
        rendered = stream.getvalue()
        assert "agent" in rendered
        # A rule renders box-drawing horizontal characters.
        assert "─" in rendered

    async def test_start_agent_turn_separates_from_previous_stream(self) -> None:
        """A turn rule must start on its own line, not glued to the
        previous chunk of streamed agent text."""
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.display("trailing token without newline")
        await sink.start_agent_turn()
        rendered = stream.getvalue()
        assert "trailing token without newline\n" in rendered

    async def test_request_permission_returns_selected_option_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        options = [
            PermissionOption(id="allow", label="Allow"),
            PermissionOption(id="deny", label="Deny"),
        ]
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "2")
        chosen = await sink.request_permission("run rm -rf?", options)
        assert chosen == "deny"
        rendered = stream.getvalue()
        assert "run rm -rf?" in rendered
        assert "Allow" in rendered
        assert "Deny" in rendered

    async def test_request_permission_defaults_first_on_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        options = [
            PermissionOption(id="allow", label="Allow"),
            PermissionOption(id="deny", label="Deny"),
        ]
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "")
        chosen = await sink.request_permission("ok?", options)
        assert chosen == "allow"

    async def test_request_permission_rejects_out_of_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        options = [PermissionOption(id="allow", label="Allow")]
        answers = iter(["99", "1"])
        monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))
        chosen = await sink.request_permission("ok?", options)
        assert chosen == "allow"


class TestPromptSinkProtocol:
    def test_terminal_sink_satisfies_protocol(self) -> None:
        sink: PromptSink = TerminalPromptSink()
        assert hasattr(sink, "display")
        assert hasattr(sink, "request_input")
        assert hasattr(sink, "request_permission")
