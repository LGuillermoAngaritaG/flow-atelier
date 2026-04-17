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

from rich.console import Console


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

    async def start_agent_turn(self, label: str = "agent") -> None:
        """Optional: print a visual marker that a new agent turn is starting.

        Called by interactive harness executors immediately before each
        ``conn.prompt(...)`` so the terminal UI can bracket each turn
        with a divider. Sinks that don't render visually may no-op.
        """
        ...


class TerminalPromptSink:
    """Default :class:`PromptSink` backed by ``stdout``/``stdin``.

    Agent token chunks are streamed raw to ``out`` (preserving the live
    feel). Turn-boundary markers, the user-turn prompt, and permission
    menus are rendered through a Rich :class:`Console` so they share the
    same visual language as the rest of the CLI (panels, tables).

    :param out: stream for :meth:`display` output (defaults to
        ``sys.stdout``); the Rich console writes to the same stream so
        styled rules and raw stream chunks interleave correctly
    :param console: optional Rich console override (mostly for tests)
    """

    def __init__(
        self,
        out: TextIO | None = None,
        console: Console | None = None,
    ) -> None:
        self._out = out if out is not None else sys.stdout
        self._console = (
            console
            if console is not None
            else Console(file=self._out, soft_wrap=True)
        )

    async def display(self, text: str) -> None:
        """Stream ``text`` to the output verbatim.

        Agent output arrives as token-sized chunks, so this is a raw
        passthrough: no newline insertion, no prefix. Callers are
        responsible for any terminal formatting.
        """
        self._out.write(text)
        self._out.flush()

    async def start_agent_turn(self, label: str = "agent") -> None:
        """Print a styled rule announcing a new agent turn.

        Always prefixed with a blank line so the rule is cleanly
        separated from any previous raw stream output.
        """
        self._out.write("\n")
        self._out.flush()
        self._console.rule(
            f"[bold cyan]🤖 {label}[/bold cyan]",
            align="left",
            style="cyan",
        )

    async def request_input(self, prompt: str) -> str:
        """Render a styled "your turn" rule, then read one line of input.

        - On a TTY: shows the ``› `` cursor; the terminal echoes the
          user's keystrokes naturally.
        - When stdin is piped (scripted runs): the consumed line is
          echoed back as ``› <answer>`` so transcripts read cleanly.
        """
        self._out.write("\n")
        self._out.flush()
        self._console.rule(
            "[bold green]👤 you[/bold green]", align="left", style="green"
        )
        if prompt and prompt.strip():
            self._console.print(f"[dim]{prompt.strip()}[/dim]")
        if sys.stdin.isatty():
            answer = await asyncio.to_thread(builtins.input, "› ")
        else:
            answer = await asyncio.to_thread(builtins.input)
            self._console.print(f"[green]›[/green] {answer}")
        return answer

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        if not options:
            raise ValueError("request_permission requires at least one option")
        self._console.rule(
            "[bold yellow]🔐 permission[/bold yellow]",
            align="left",
            style="yellow",
        )
        self._console.print(summary)
        for idx, opt in enumerate(options, start=1):
            self._console.print(f"  [bold]{idx})[/bold] {opt.label}")

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
                self._console.print("[yellow]  invalid input, try again[/yellow]")
                continue
            if 1 <= choice <= len(options):
                return options[choice - 1].id
            self._console.print(
                f"[yellow]  out of range (1-{len(options)}), try again[/yellow]"
            )
