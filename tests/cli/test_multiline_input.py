"""Tests for multiline_input helper."""
from __future__ import annotations

import builtins
import sys

import pytest


class TestMultilineInputNonTTY:
    """Non-TTY fallback delegates to builtins.input()."""

    async def test_async_returns_builtin_input_result(self, monkeypatch):
        from app.cli.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(builtins, "input", lambda prompt="": "piped answer")
        result = await multiline_input("› ")
        assert result == "piped answer"

    def test_sync_returns_builtin_input_result(self, monkeypatch):
        from app.cli.multiline_input import multiline_input_sync

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(builtins, "input", lambda prompt="": "sync piped")
        result = multiline_input_sync("› ")
        assert result == "sync piped"


class TestMultilineInputTTY:
    """TTY path uses prompt_toolkit."""

    async def test_tty_calls_prompt_toolkit(self, monkeypatch):
        from app.cli.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        class FakeSession:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def prompt(self, message="", **kwargs):
                return "multiline text\nsecond line"

        monkeypatch.setattr(
            "app.cli.multiline_input.PromptSession", FakeSession
        )
        result = await multiline_input("› ", hint="Alt+Enter to submit")
        assert result == "multiline text\nsecond line"

    async def test_hint_printed_on_tty(self, monkeypatch, capsys):
        from app.cli.multiline_input import multiline_input

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        class FakeSession:
            def __init__(self, **kwargs):
                pass

            def prompt(self, message="", **kwargs):
                return "answer"

        monkeypatch.setattr(
            "app.cli.multiline_input.PromptSession", FakeSession
        )
        await multiline_input("› ", hint="Alt+Enter to submit")
        captured = capsys.readouterr()
        assert "Alt+Enter to submit" in captured.out
