"""PromptSink — pluggable user-interaction surface for executors.

Executors that need to talk to the user (ACP harnesses, future elicitation)
route all display and input calls through a :class:`PromptSink`.
The terminal implementation writes to a stream and reads stdin. Future
transports (websocket, queue-based API) implement the same protocol.
"""

from __future__ import annotations

import asyncio
import builtins
import sys
from collections import Counter
from typing import TYPE_CHECKING, Protocol, TextIO, runtime_checkable

from rich.console import Console
from rich.markup import escape
from rich.text import Text

if TYPE_CHECKING:
    from flow_atelier.schemas.log import IntermediateStep


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
        self._console = console if console is not None else Console(file=self._out, soft_wrap=True)
        # Widest task name seen so far, so the step lines keep a straight
        # tool column. A running max rather than a precomputed width: the
        # sink is handed steps, never the conduit.
        self._task_width = 0
        # Tool calls seen since each task's last non-tool step, tallied so a
        # long run of them collapses to one summary line. Keyed by owning task:
        # one sink is shared by every executor, and `max_concurrency` defaults
        # to 3, so a single shared counter would pool calls from tasks running
        # in parallel and bill the whole tally to whichever task happened to
        # flush it.
        self._tool_bursts: dict[str, Counter[str]] = {}

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
        self._console.rule("[bold green]👤 you[/bold green]", align="left", style="green")
        if prompt and prompt.strip():
            self._console.print(f"[dim]{escape(prompt.strip())}[/dim]")
        if sys.stdin.isatty():
            from flow_atelier.cli.rendering.multiline_input import multiline_input

            answer = await multiline_input("› ", hint="Alt+Enter to submit")
        else:
            answer = await asyncio.to_thread(builtins.input)
            self._console.print(f"[green]›[/green] {escape(answer)}")
        return answer

    def _tag(self, timestamp: str | None = None, task: str | None = None) -> tuple[Text, str]:
        """Return the timestamp prefix and padded task tag for one line.

        :param timestamp: ISO timestamp to stamp, or ``None`` for now.
        :param task: owning task name; defaults to the engine ContextVar.
            Passed explicitly when the line describes work that finished
            earlier (a burst tally), so it is labelled with the task that
            actually did it rather than whoever is current at flush time.
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
        name = current_task() if task is None else task
        self._task_width = max(self._task_width, len(name))
        return (
            Text(f"{clock} ", style="dim"),
            name.ljust(self._task_width),
        )

    async def _flush_tool_burst(self, task: str) -> None:
        """Emit the tally for ``task``'s run of tool calls, if it has one.

        Only that task's burst: tasks running concurrently each keep their
        own tally, so one task reaching a turn boundary never closes out —
        or takes credit for — another's in-flight calls.

        :param task: owning task name whose burst should be closed.
        """
        counts = self._tool_bursts.pop(task, None)
        if not counts:
            return
        from flow_atelier.cli.rendering.render import render_tool_burst_summary

        prefix, tag = self._tag(task=task)
        prefix.append(render_tool_burst_summary(counts, task=tag))
        self._console.print(prefix)

    async def flush_steps(self) -> None:
        """Close out the current task's open tool burst at a turn boundary.

        Called by the harness driver after each prompt round, inside the
        owning task's context, so a task that ends mid-burst still reports
        how many tools it used without disturbing its peers.
        """
        from flow_atelier.modules.engine import current_task

        await self._flush_tool_burst(current_task())

    async def display_message(self, text: str) -> None:
        """Show a preview of what the agent said.

        :param text: agent message text.
        """
        from flow_atelier.cli._shared import mark_activity
        from flow_atelier.cli.rendering.render import render_agent_message
        from flow_atelier.modules.engine import current_task

        if not text.strip():
            return
        await self._flush_tool_burst(current_task())
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
        from flow_atelier.modules.engine import current_task
        from flow_atelier.schemas.log import StepKind

        if step.kind == StepKind.tool_result and step.tool_status != "failed":
            return
        mark_activity()
        owner = current_task()

        if step.kind == StepKind.tool_call:
            burst = self._tool_bursts.get(owner)
            if burst is None:
                burst = self._tool_bursts[owner] = Counter()
                prefix, task = self._tag(step.timestamp)
                prefix.append(render_tool_burst_start(task=task))
                self._console.print(prefix)
            burst[step.tool_name or "tool"] += 1
            return

        # Anything else ends this task's burst and gets rendered normally.
        await self._flush_tool_burst(owner)
        prefix, task = self._tag(step.timestamp)
        prefix.append(_render_step(step, task=task))
        self._console.print(prefix)


class StreamPromptSink:
    """:class:`PromptSink` that emits one JSON object per line on stdout.

    Selected by ``atelier ask --json`` so a programmatic caller (another
    agent, a script) can drive an interactive session over stdio: agent
    chunks, the agent's questions, intermediate steps, and the terminal
    flow result all arrive as parseable NDJSON, and each question is
    answered with one line on stdin.

    The vocabulary mirrors :class:`flow_atelier.services.api.ws_sink.WsPromptSink`
    (``agent_message`` / ``agent_input_request`` / ``step``) so a caller
    uses one mental model whether it connects to the server or shells out
    to the CLI.

    The done marker can arrive **split across token chunks** (e.g. ``"["``,
    ``"ATELIER_"``, ``"DONE]"``) because LLM tokenizers don't respect the
    marker's boundaries. A per-chunk ``.replace()`` therefore can't catch it.
    This sink buffers a small tail that could be the start of the marker,
    strips the complete marker when it forms, and flushes the held tail at
    turn boundaries (via :meth:`flush_steps`) so no real text is lost.

    :param out: stream for NDJSON output; defaults to :data:`sys.stdout`.
    :param inp: stream for replies; defaults to :data:`sys.stdin`.
    :param done_marker: sentinel whose presence ends an interactive loop.
        Stripped from emitted ``agent_message`` text so it never leaks to a
        programmatic caller.
    """

    def __init__(
        self,
        out: TextIO | None = None,
        inp: TextIO | None = None,
        done_marker: str = "[ATELIER_DONE]",
    ) -> None:
        """Initialize the streaming sink.

        :param out: stream for NDJSON output; defaults to :data:`sys.stdout`.
        :param inp: stream for replies; defaults to :data:`sys.stdin`.
        :param done_marker: sentinel stripped from streamed agent text.
        """
        self._out = out if out is not None else sys.stdout
        self._inp = inp if inp is not None else sys.stdin
        self._done_marker = done_marker
        # Monotonic per-flow request id. A CLI flow is strictly ordered —
        # the harness awaits each request_input() before issuing the next —
        # so a simple counter is a safe correlation id.
        self._next_request_id = 1
        # Held tail that might be the prefix of a marker arriving across
        # chunk boundaries. At most ``len(marker) - 1`` chars.
        self._pending = ""

    def _emit(self, obj: dict[str, object]) -> None:
        """Write one envelope as a JSON line and flush.

        :param obj: envelope to serialize.
        """
        import json

        self._out.write(json.dumps(obj, ensure_ascii=False))
        self._out.write("\n")
        self._out.flush()

    def _split_marker(self, text: str) -> tuple[str, str]:
        """Return ``(emit_text, held_tail)`` with any marker tail held back.

        Joins ``text`` onto any previously held tail, strips a complete
        marker if present, then holds back a suffix that could be the start
        of a marker arriving across chunks.

        :param text: the incoming chunk to filter.
        :returns: the text safe to emit now and the tail to hold back.
        """
        buf = self._pending + text
        self._pending = ""
        # Strip a complete marker if it has formed.
        buf = buf.replace(self._done_marker, "")
        # Hold back a tail that could be the *start* of a marker. The
        # longest such tail is one char shorter than the marker: anything
        # that length or longer would already match the full marker.
        n = len(self._done_marker)
        hold = min(len(buf), n - 1)
        # Pick the longest suffix that is a prefix of the marker.
        emit_end = len(buf)
        for length in range(hold, 0, -1):
            if self._done_marker.startswith(buf[-length:]):
                emit_end = len(buf) - length
                break
        emit_text = buf[:emit_end]
        held = buf[emit_end:]
        self._pending = held
        return emit_text, held

    async def display(self, text: str) -> None:
        """Stream one agent-prose chunk as an ``agent_message`` envelope.

        Marker fragments are held back so a split ``[ATELIER_DONE]`` never
        reaches the caller; the held tail is flushed at the next turn
        boundary by :meth:`flush_steps`.

        :param text: agent text chunk to filter and forward.
        """
        from flow_atelier.modules.engine import current_task

        emit_text, _ = self._split_marker(text)
        if emit_text:
            self._emit(
                {
                    "type": "agent_message",
                    "task": current_task(""),
                    "text": emit_text,
                }
            )

    async def start_agent_turn(self, label: str = "agent") -> None:
        """No-op for the streaming sink.

        :param label: turn label (ignored).
        """

    async def request_input(self, prompt: str) -> str:
        """Emit an ``agent_input_request`` and read one reply line from stdin.

        The next line of stdin (trailing newline stripped) is the caller's
        reply. EOF raises :class:`EOFError`, which the harness surfaces as
        ``"interactive input unavailable: ..."``.

        :param prompt: prompt label shown to the user.
        :returns: the caller's reply.
        :raises EOFError: if stdin is closed before a line is available.
        """
        from flow_atelier.modules.engine import current_task

        request_id = str(self._next_request_id)
        self._next_request_id += 1
        self._emit(
            {
                "type": "agent_input_request",
                "task": current_task(""),
                "request_id": request_id,
                "prompt": prompt,
            }
        )
        answer = await asyncio.to_thread(self._inp.readline)
        if answer == "":  # EOF before any content
            raise EOFError("stdin closed while waiting for agent input")
        return answer.rstrip("\n")

    async def display_step(self, step: IntermediateStep) -> None:
        """Forward an intermediate step as a ``step`` envelope.

        :param step: the :class:`IntermediateStep` to forward.
        """
        from flow_atelier.modules.engine import current_task

        self._emit(
            {
                "type": "step",
                "task": current_task(""),
                "step": step.model_dump(mode="json"),
            }
        )

    async def display_message(self, text: str) -> None:
        """Forward a batched agent message as an ``agent_message`` envelope.

        :param text: agent message text.
        """
        if text.strip():
            await self.display(text)

    async def flush_steps(self) -> None:
        """Emit any marker-tail held back at a turn boundary.

        Whatever was retained as a possible marker prefix but did not grow
        into the full marker is real text; flush it now so it isn't lost.
        """
        if self._pending:
            from flow_atelier.modules.engine import current_task

            held = self._pending
            self._pending = ""
            self._emit(
                {
                    "type": "agent_message",
                    "task": current_task(""),
                    "text": held,
                }
            )
