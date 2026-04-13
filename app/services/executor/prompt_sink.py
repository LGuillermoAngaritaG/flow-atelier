"""PromptSink — pluggable user-interaction surface for executors.

Executors that need to talk to the user (ACP harnesses, future elicitation)
route all display/input/permission calls through a :class:`PromptSink`.
The terminal implementation writes to a stream and reads stdin. Future
transports (websocket, queue-based API) implement the same protocol.
"""
from __future__ import annotations

import asyncio
import builtins
import sys
from dataclasses import dataclass
from typing import Protocol, TextIO, runtime_checkable


@dataclass(frozen=True)
class PermissionOption:
    """One choice offered to the user for a permission decision.

    :param id: stable identifier returned to the caller on selection
    :param label: human-readable label shown in the UI
    """

    id: str
    label: str


@runtime_checkable
class PromptSink(Protocol):
    """Surface through which an executor interacts with the human user.

    All methods are async so API-backed sinks can suspend on I/O.
    """

    async def display(self, text: str) -> None:
        """Show text to the user (streamed agent output, system messages)."""
        ...

    async def request_input(self, prompt: str) -> str:
        """Ask the user for a free-form reply and return their response."""
        ...

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        """Ask the user to pick one of ``options``; return the chosen ``id``."""
        ...


class TerminalPromptSink:
    """Default :class:`PromptSink` backed by ``stdout``/``stdin``.

    :param out: stream for :meth:`display` output (defaults to ``sys.stdout``)
    """

    def __init__(self, out: TextIO | None = None) -> None:
        self._out = out if out is not None else sys.stdout

    async def display(self, text: str) -> None:
        """Stream ``text`` to the output verbatim.

        Agent output arrives as token-sized chunks, so this is a raw
        passthrough: no newline insertion, no prefix. Callers are
        responsible for any terminal formatting.
        """
        self._out.write(text)
        self._out.flush()

    async def request_input(self, prompt: str) -> str:
        """Ask the user for a reply with a clear visual break.

        Inserts a blank line + horizontal rule before the prompt so the
        user can tell exactly when streamed agent output has stopped and
        it's their turn to type.
        """
        self._out.write("\n\n─── your turn ───\n")
        self._out.write(prompt)
        if not prompt.endswith("\n"):
            self._out.write("\n")
        self._out.flush()
        return await asyncio.to_thread(builtins.input, "> ")

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        if not options:
            raise ValueError("request_permission requires at least one option")
        self._out.write(summary)
        if not summary.endswith("\n"):
            self._out.write("\n")
        for idx, opt in enumerate(options, start=1):
            self._out.write(f"  {idx}) {opt.label}\n")
        self._out.flush()

        while True:
            raw = await asyncio.to_thread(
                builtins.input, f"choose [1-{len(options)}, default 1]: "
            )
            raw = raw.strip()
            if raw == "":
                return options[0].id
            try:
                choice = int(raw)
            except ValueError:
                self._out.write("  invalid input, try again\n")
                self._out.flush()
                continue
            if 1 <= choice <= len(options):
                return options[choice - 1].id
            self._out.write(
                f"  out of range (1-{len(options)}), try again\n"
            )
            self._out.flush()
