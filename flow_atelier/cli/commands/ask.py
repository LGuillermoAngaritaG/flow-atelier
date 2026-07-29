"""`atelier ask` command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
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
) -> None:
    """Start an interactive Claude conversation in a target directory.

    Claude's replies stream to the terminal. When Claude asks a question,
    type the answer at the prompt; the same ACP session continues until
    Claude signals that it is finished.

    :param query: initial question or task sent to Claude.
    :param path: working directory passed to Claude's ACP session.
    """
    if not query.strip():
        console.print("[red]error:[/red] query cannot be empty")
        raise typer.Exit(code=2)

    atelier = Atelier()
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

    problems = atelier.tool_readiness(conduit)
    if problems:
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
        render_task_event(event, console)

    def _on_started(flow_id: str) -> None:
        """Capture and display the newly allocated flow id.

        :param flow_id: flow id assigned by the engine.
        """
        captured_flow_id["id"] = flow_id
        console.print(_render_orchestration_msg(f"starting flow {flow_id}"))

    def _on_task_starting(task_name: str, tool: str) -> None:
        """Display the task start banner.

        :param task_name: name of the task beginning execution.
        :param tool: executor selected for the task.
        """
        index = running.start(task_name)
        mark_activity()
        console.print()
        console.print(render_task_start(task_name, tool, index, 1))

    target = path.resolve()
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
            )
        )
    except asyncio.CancelledError:
        render_run_footer(collected_events, console)
        console.print("[yellow]flow stopped[/yellow]")
        stopped_id = captured_flow_id["id"]
        if stopped_id:
            console.print(f"[yellow]flow_id:[/yellow] {stopped_id}")
        raise typer.Exit(code=0)
    except Exception as exc:  # noqa: BLE001
        render_run_footer(collected_events, console)
        console.print(f"[red]flow failed:[/red] {escape(str(exc))}")
        failed_id = captured_flow_id["id"]
        if failed_id:
            console.print(f"[red]flow_id:[/red] {failed_id}")
        raise typer.Exit(code=1)

    render_run_footer(collected_events, console)
    console.print(f"[green]flow_id:[/green] {flow_id}")
