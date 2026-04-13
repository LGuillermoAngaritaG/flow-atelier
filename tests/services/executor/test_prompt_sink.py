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
        the turn-over prompt; otherwise the '> ' gets glued onto the last
        agent token."""
        stream = io.StringIO()
        sink = TerminalPromptSink(out=stream)
        await sink.display("agent finished mid-sentence")
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "ok")
        await sink.request_input("reply?")
        rendered = stream.getvalue()
        # A blank line separates the streamed text from the prompt.
        assert "agent finished mid-sentence\n\n" in rendered
        assert "reply?" in rendered

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
