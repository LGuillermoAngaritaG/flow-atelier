"""`atelier ask` command."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from flow_atelier.cli._shared import console, mark_activity
from flow_atelier.cli.commands.run import _RunningTasks, _with_heartbeat
from flow_atelier.cli.main import app
from flow_atelier.cli.rendering.render import (
    _render_orchestration_msg,
    render_run_footer,
    render_task_event,
    render_task_start,
)
from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.conduit import Conduit, TaskDefinition
from flow_atelier.schemas.log import TaskEvent
from flow_atelier.services.executor.prompt_sink import StreamPromptSink


@app.command("ask")
def ask_cmd(
    query: str = typer.Argument(
        ...,
        help="Initial question or task to send to Claude.",
    ),
    path: Path = typer.Option(
        ...,
        "--path",
        "-p",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Working directory Claude can inspect and modify.",
    ),
    json_mode: bool = typer.Option(
        False,
        "--json",
        help=(
            "Emit one JSON object per line on stdout instead of the rich "
            "console view, and read replies line-by-line from stdin. "
            "Event types: agent_message, agent_input_request, step, "
            "flow_complete, flow_failed. For agent-to-agent callers."
        ),
    ),
) -> None:
    """Start an interactive Claude conversation in a target directory.

    Claude's replies stream to the terminal. When Claude asks a question,
    type the answer at the prompt; the same ACP session continues until
    Claude signals that it is finished.

    With ``--json`` the conversation is machine-readable: each event is one
    JSON line on stdout and each reply is one line on stdin, so another
    agent can drive the session programmatically.

    :param query: initial question or task sent to Claude.
    :param path: working directory passed to Claude's ACP session.
    :param json_mode: emit NDJSON events on stdout and read stdin replies.
    """
    if not query.strip():
        console.print("[red]error:[/red] query cannot be empty")
        raise typer.Exit(code=2)

    from flow_atelier.core.settings import AtelierSettings

    settings = AtelierSettings()
    sink = StreamPromptSink(done_marker=settings.done_marker) if json_mode else None
    atelier = Atelier(settings=settings, prompt_sink=sink)
    conduit = Conduit(
        name="ask",
        description="Interactive Claude conversation.",
        max_concurrency=1,
        tasks=[
            TaskDefinition(
                name="chat",
                description="Ask Claude",
                task=query,
                tool="harness:claude-code",
                depends_on=[],
                interactive=True,
            )
        ],
    )

    # In JSON mode, build a stderr-bound console so the heartbeat and any
    # diagnostics land where a programmatic caller won't parse them as NDJSON.
    # ``Console.print`` has no per-call ``stderr=`` switch, so the binding
    # must happen at construction (verified to survive asyncio + subprocess).
    stderr_console = Console(stderr=True) if json_mode else None

    problems = atelier.tool_readiness(conduit)
    if problems:
        if json_mode:
            # Diagnostics go to stderr so stdout stays pure NDJSON.
            for problem in problems:
                stderr_console.print(f"cannot run: {problem}", style="red")
        else:
            for problem in problems:
                console.print(f"[red]cannot run:[/red] {escape(problem)}")
        raise typer.Exit(code=1)

    collected_events: list[TaskEvent] = []
    captured_flow_id: dict[str, str | None] = {"id": None}
    running = _RunningTasks()

    def _on_event(event: TaskEvent) -> None:
        """Collect and render the completed task event.

        :param event: task event emitted by the engine.
        """
        collected_events.append(event)
        running.finish(event)
        mark_activity()
        if not json_mode:
            render_task_event(event, console)

    def _on_started(flow_id: str) -> None:
        """Capture and display the newly allocated flow id.

        :param flow_id: flow id assigned by the engine.
        """
        captured_flow_id["id"] = flow_id
        if not json_mode:
            console.print(_render_orchestration_msg(f"starting flow {flow_id}"))

    def _on_task_starting(task_name: str, tool: str) -> None:
        """Display the task start banner.

        :param task_name: name of the task beginning execution.
        :param tool: executor selected for the task.
        """
        index = running.start(task_name)
        mark_activity()
        if not json_mode:
            console.print()
            console.print(render_task_start(task_name, tool, index, 1))

    target = path.resolve()
    if not json_mode:
        console.print(_render_orchestration_msg(f'asking Claude in "{target}"'))
    try:
        flow_id = asyncio.run(
            _with_heartbeat(
                atelier.engine.run(
                    conduit,
                    {},
                    on_task_event=_on_event,
                    on_flow_started=_on_started,
                    on_task_starting=_on_task_starting,
                    working_dir=target,
                    stoppable=True,
                ),
                running,
                # Route the heartbeat to stderr in JSON mode so it never
                # pollutes the NDJSON stream on stdout.
                beat_console=stderr_console,
            )
        )
    except asyncio.CancelledError:
        _finish(collected_events, json_mode, status="stopped", flow_id=captured_flow_id["id"])
        raise typer.Exit(code=0)
    except Exception as exc:  # noqa: BLE001
        _finish(
            collected_events,
            json_mode,
            status="failed",
            flow_id=captured_flow_id["id"],
            error=str(exc),
        )
        raise typer.Exit(code=1)

    _finish(collected_events, json_mode, status="complete", flow_id=flow_id)


def _finish(
    events: list[TaskEvent],
    json_mode: bool,
    status: str,
    flow_id: str | None,
    error: str | None = None,
) -> None:
    """Emit the terminal footer for the run.

    In ``--json`` mode this is one final envelope on stdout
    (``flow_complete`` / ``flow_failed``). Otherwise it renders the rich
    console footer used by the human-facing CLI.

    :param events: task events collected during the run.
    :param json_mode: whether NDJSON output is active.
    :param status: one of ``complete`` / ``failed`` / ``stopped``.
    :param flow_id: flow id, if one was allocated.
    :param error: error message, on failure.
    """
    if json_mode:
        if status == "complete":
            envelope = {"type": "flow_complete", "flow_id": flow_id or ""}
        else:
            # Collapse newlines so the envelope stays one NDJSON line: the
            # engine's failure string can carry a multi-line traceback.
            clean_error = (error or status).replace("\n", " ").replace("\r", " ").strip()
            envelope = {
                "type": "flow_failed",
                "flow_id": flow_id or "",
                "error": clean_error,
            }
        # Write raw — Rich's console wraps long lines at terminal width,
        # which would break the one-JSON-object-per-line invariant.
        print(json.dumps(envelope, ensure_ascii=False), flush=True)
        return

    render_run_footer(events, console)
    if status == "complete":
        console.print(f"[green]flow_id:[/green] {flow_id}")
    elif status == "stopped":
        console.print("[yellow]flow stopped[/yellow]")
        if flow_id:
            console.print(f"[yellow]flow_id:[/yellow] {flow_id}")
    else:
        console.print(f"[red]flow failed:[/red] {escape(error or '')}")
        if flow_id:
            console.print(f"[red]flow_id:[/red] {flow_id}")
