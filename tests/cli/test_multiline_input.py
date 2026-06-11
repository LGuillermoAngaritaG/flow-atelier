"""Tests for multiline_input helper."""
from __future__ import annotations

import builtins
import sys


class TestMultilineInputNonTTY:
    """Non-TTY fallback delegates to builtins.input()."""

    async def test_async_returns_builtin_input_result(self, monkeypatch):
        """Verify multiline_input falls back to builtins.input on non-TTY.

        :param monkeypatch: pytest monkeypatch fixture.
        """
        from flow_atelier.cli.rendering.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(builtins, "input", lambda prompt="": "piped answer")
        result = await multiline_input("› ")
        assert result == "piped answer"

    def test_sync_returns_builtin_input_result(self, monkeypatch):
        """Verify multiline_input_sync falls back to builtins.input on non-TTY.

        :param monkeypatch: pytest monkeypatch fixture.
        """
        from flow_atelier.cli.rendering.multiline_input import multiline_input_sync

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(builtins, "input", lambda prompt="": "sync piped")
        result = multiline_input_sync("› ")
        assert result == "sync piped"


class TestMultilineInputTTY:
    """TTY path uses prompt_toolkit."""

    async def test_tty_calls_prompt_toolkit(self, monkeypatch):
        """Verify multiline_input delegates to PromptSession on TTY.

        :param monkeypatch: pytest monkeypatch fixture.
        """
        from flow_atelier.cli.rendering.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        class FakeSession:
            def __init__(self, **kwargs):
                """Capture PromptSession constructor kwargs.

                :param kwargs: forwarded constructor keyword arguments.
                """
                self.kwargs = kwargs

            def prompt(self, message="", **kwargs):
                """Return a canned multiline prompt response.

                :param message: prompt message (ignored).
                :param kwargs: forwarded prompt keyword arguments.
                """
                return "multiline text\nsecond line"

        monkeypatch.setattr(
            "flow_atelier.cli.rendering.multiline_input.PromptSession", FakeSession
        )
        result = await multiline_input("› ", hint="Alt+Enter to submit")
        assert result == "multiline text\nsecond line"

    async def test_hint_printed_on_tty(self, monkeypatch, capsys):
        """Verify the hint message is printed when running on a TTY.

        :param monkeypatch: pytest monkeypatch fixture.
        :param capsys: pytest capsys fixture for stdout capture.
        """
        from flow_atelier.cli.rendering.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        class FakeSession:
            def __init__(self, **kwargs):
                """Accept PromptSession constructor kwargs.

                :param kwargs: forwarded constructor keyword arguments.
                """
                pass

            def prompt(self, message="", **kwargs):
                """Return a canned prompt response.

                :param message: prompt message (ignored).
                :param kwargs: forwarded prompt keyword arguments.
                """
                return "answer"

        monkeypatch.setattr(
            "flow_atelier.cli.rendering.multiline_input.PromptSession", FakeSession
        )
        await multiline_input("› ", hint="Alt+Enter to submit")
        captured = capsys.readouterr()
        assert "Alt+Enter to submit" in captured.out
