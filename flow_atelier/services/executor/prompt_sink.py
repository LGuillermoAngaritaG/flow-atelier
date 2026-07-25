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
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TextIO, runtime_checkable

from rich.console import Console
from rich.markup import escape
from rich.text import Text

if TYPE_CHECKING:
    from flow_atelier.schemas.log import IntermediateStep


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
        """Show text to the user (streamed agent output, system messages).

        :param text: text to render to the user.
        """
        ...

    async def request_input(self, prompt: str) -> str:
        """Ask the user for a free-form reply and return their response.

        :param prompt: prompt label shown to the user.
        :returns: the user's reply.
        """
        ...

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        """Ask the user to pick one of ``options``; return the chosen ``id``.

        :param summary: human-readable description of the pending action.
        :param options: list of selectable :class:`PermissionOption` choices.
        :returns: the ``id`` of the option the user picked.
        """
        ...

    async def start_agent_turn(self, label: str = "agent") -> None:
        """Optional: print a visual marker that a new agent turn is starting.

        Called by interactive harness executors immediately before each
        ``conn.prompt(...)`` so the terminal UI can bracket each turn
        with a divider. Sinks that don't render visually may no-op.

        :param label: label shown in the turn divider (default ``"agent"``).
        """
        ...

    async def display_step(self, step: IntermediateStep) -> None:
        """Optional: show an intermediate step (thinking, tool call, tool result).

        Called by harness executors when ``stream_steps=True`` to surface
        agent progress as it happens. Sinks that don't render visually
        may no-op.

        :param step: the :class:`IntermediateStep` to render.
        """
        ...

    async def display_message(self, text: str) -> None:
        """Optional: show what the agent said, for non-interactive runs.

        Interactive tasks stream raw chunks through :meth:`display`; this
        is the batched equivalent for runs that only surface steps, so the
        agent's narration appears between its tool activity.

        :param text: agent message text.
        """
        ...

    async def flush_steps(self) -> None:
        """Optional: close out any coalesced display state at a turn boundary.

        Sinks that batch output (e.g. collapsing runs of tool calls) get a
        chance to emit their summary before the task ends.
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
        """Initialize the terminal prompt sink.

        :param out: optional output stream; defaults to ``sys.stdout``.
        :param console: optional Rich console override; defaults to a new
            console writing to ``out``.
        """
        self._out = out if out is not None else sys.stdout
        self._console = (
            console
            if console is not None
            else Console(file=self._out, soft_wrap=True)
        )
        # Widest task name seen so far, so the step lines keep a straight
        # tool column. A running max rather than a precomputed width: the
        # sink is handed steps, never the conduit.
        self._task_width = 0
        # Tool calls seen since the last non-tool step, tallied so a long
        # run of them collapses to one summary line.
        self._tool_burst: Counter[str] = Counter()

    async def display(self, text: str) -> None:
        """Stream ``text`` to the output verbatim.

        Agent output arrives as token-sized chunks, so this is a raw
        passthrough: no newline insertion, no prefix. Callers are
        responsible for any terminal formatting.

        :param text: text to write to the output stream.
        """
        from flow_atelier.cli._shared import mark_activity

        self._out.write(text)
        self._out.flush()
        mark_activity()

    async def start_agent_turn(self, label: str = "agent") -> None:
        """Print a styled rule announcing a new agent turn.

        Always prefixed with a blank line so the rule is cleanly
        separated from any previous raw stream output.

        :param label: label shown inside the rule (default ``"agent"``).
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

        :param prompt: dim hint text shown above the input cursor.
        :returns: the user's reply.
        """
        self._out.write("\n")
        self._out.flush()
        self._console.rule(
            "[bold green]👤 you[/bold green]", align="left", style="green"
        )
        if prompt and prompt.strip():
            self._console.print(f"[dim]{escape(prompt.strip())}[/dim]")
        if sys.stdin.isatty():
            from flow_atelier.cli.rendering.multiline_input import multiline_input

            answer = await multiline_input("› ", hint="Alt+Enter to submit")
        else:
            answer = await asyncio.to_thread(builtins.input)
            self._console.print(f"[green]›[/green] {escape(answer)}")
        return answer

    def _tag(self, timestamp: str | None = None) -> tuple[Text, str]:
        """Return the timestamp prefix and padded task tag for one line.

        :param timestamp: ISO timestamp to stamp, or ``None`` for now.
        :returns: tuple of the stamped prefix and the padded task name.
        """
        from datetime import datetime

        from flow_atelier.cli._shared import _format_clock_short
        from flow_atelier.modules.engine import current_task

        # Lines we synthesize (message previews, burst tallies) carry no step
        # timestamp; they are happening now, so stamp them now rather than
        # rendering the "unknown" dash.
        clock = (
            _format_clock_short(timestamp)
            if timestamp
            else datetime.now().astimezone().strftime("%H:%M")
        )
        task = current_task()
        self._task_width = max(self._task_width, len(task))
        return (
            Text(f"{clock} ", style="dim"),
            task.ljust(self._task_width),
        )

    async def _flush_tool_burst(self) -> None:
        """Emit the tally for the run of tool calls just finished, if any."""
        if not self._tool_burst:
            return
        from flow_atelier.cli.rendering.render import render_tool_burst_summary

        counts, self._tool_burst = self._tool_burst, Counter()
        prefix, task = self._tag()
        prefix.append(render_tool_burst_summary(counts, task=task))
        self._console.print(prefix)

    async def flush_steps(self) -> None:
        """Close out any open tool burst at a turn boundary.

        Called by the harness driver after each prompt round so a task that
        ends mid-burst still reports how many tools it used.
        """
        await self._flush_tool_burst()

    async def display_message(self, text: str) -> None:
        """Show a preview of what the agent said.

        :param text: agent message text.
        """
        from flow_atelier.cli._shared import mark_activity
        from flow_atelier.cli.rendering.render import render_agent_message

        if not text.strip():
            return
        await self._flush_tool_burst()
        mark_activity()
        prefix, task = self._tag()
        prefix.append(render_agent_message(text, task=task))
        self._console.print(prefix)

    async def display_step(self, step: IntermediateStep) -> None:
        """Render an intermediate step, collapsing runs of tool calls.

        An agent that makes forty tool calls in a row would otherwise push
        everything else off screen, so consecutive calls collapse to a
        ``using tools…`` marker plus a closing tally. Successful tool
        results are dropped outright — live, ``✓ completed`` says nothing the
        next line doesn't imply. Failures always show.

        This is the live view only. Per-call detail with arguments is still
        recorded and rendered in full by ``atelier logs --show steps``.

        Lines are tagged with the owning task (via the engine ContextVar, as
        :class:`WsPromptSink` does) so steps stay attributable when several
        tasks run concurrently, and stamped ``HH:MM`` so a long-running call
        is visibly long-running.

        :param step: the :class:`IntermediateStep` to render.
        """
        from flow_atelier.cli._shared import mark_activity
        from flow_atelier.cli.rendering.render import (
            _render_step,
            render_tool_burst_start,
        )
        from flow_atelier.schemas.log import StepKind

        if step.kind == StepKind.tool_result and step.tool_status != "failed":
            return
        mark_activity()

        if step.kind == StepKind.tool_call:
            if not self._tool_burst:
                prefix, task = self._tag(step.timestamp)
                prefix.append(render_tool_burst_start(task=task))
                self._console.print(prefix)
            self._tool_burst[step.tool_name or "tool"] += 1
            return

        # Anything else ends the burst and gets rendered normally.
        await self._flush_tool_burst()
        prefix, task = self._tag(step.timestamp)
        prefix.append(_render_step(step, task=task))
        self._console.print(prefix)

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        """Prompt the user to choose one of ``options`` and return its id.

        :param summary: human-readable description of the pending action.
        :param options: list of selectable :class:`PermissionOption` choices.
        :returns: the ``id`` of the option the user selected.
        """
        if not options:
            raise ValueError("request_permission requires at least one option")
        self._console.rule(
            "[bold yellow]🔐 permission[/bold yellow]",
            align="left",
            style="yellow",
        )
        self._console.print(escape(summary))
        for idx, opt in enumerate(options, start=1):
            self._console.print(f"  [bold]{idx})[/bold] {escape(opt.label)}")

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
