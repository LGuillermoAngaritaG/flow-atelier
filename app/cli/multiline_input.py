"""Multi-line terminal input using prompt_toolkit.

Enter inserts a newline; Alt+Enter (Escape then Enter) submits.
Falls back to ``builtins.input()`` when stdin is not a TTY.
"""
from __future__ import annotations

import asyncio
import builtins
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


def _make_key_bindings() -> KeyBindings:
    """Alt+Enter submits; Enter inserts newline."""
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _submit(event):
        event.current_buffer.validate_and_handle()

    return kb


async def multiline_input(prompt: str = "› ", hint: str = "") -> str:
    """Read user input — multi-line on a TTY, single-line otherwise."""
    if not sys.stdin.isatty():
        return await asyncio.to_thread(builtins.input, prompt)

    if hint:
        print(f"\033[2m({hint})\033[0m", flush=True)

    session = PromptSession(multiline=True, key_bindings=_make_key_bindings())
    return await asyncio.to_thread(session.prompt, prompt)


def multiline_input_sync(prompt: str = "› ", hint: str = "") -> str:
    """Synchronous variant for use before ``asyncio.run()``."""
    if not sys.stdin.isatty():
        return builtins.input(prompt)

    if hint:
        print(f"\033[2m({hint})\033[0m", flush=True)

    session = PromptSession(multiline=True, key_bindings=_make_key_bindings())
    return session.prompt(prompt)
