"""`atelier run` command."""
from __future__ import annotations

import asyncio
import sys

import typer

from app.cli._shared import _parse_inputs, console
from app.cli.main import app
from app.cli.rendering.render import (
    _render_orchestration_msg,
    _render_run_footer,
    _render_task_event,
)
from app.core.atelier import Atelier
from app.schemas.log import TaskEvent


@app.command(
    "run",
    help="Start a new flow for the named conduit. Use --input key=value to pass inputs.",
)
def run_cmd(
    conduit_name: str = typer.Argument(..., help="Name of the conduit to run."),
    inputs_raw: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        help="key=value input (repeatable).",
    ),
    show_steps: bool = typer.Option(
        True,
        "--show-steps/--hide-steps",
        help="Stream intermediate thinking and tool activity live (default: on).",
    ),
) -> None:
    """Start a new flow for the named conduit.

    :param conduit_name: name of the conduit to execute.
    :param inputs_raw: list of ``key=value`` input strings collected from ``--input``.
    :param show_steps: when true, stream intermediate thinking and tool activity live.
    """
    inputs = _parse_inputs(inputs_raw)
    atelier = Atelier()

    # Prompt for missing inputs when running interactively.
    conduit = atelier.store.read_conduit(conduit_name)
    missing = [k for k in conduit.inputs if k not in inputs]
    if missing and sys.stdin.isatty():
        from app.cli.rendering.multiline_input import multiline_input_sync

        try:
            for key in missing:
                value = multiline_input_sync(
                    f"  {key} ({conduit.inputs[key]}): ",
                    hint="Alt+Enter to submit",
                )
                inputs[key] = value
        except KeyboardInterrupt:
            print()
            raise typer.Exit(code=130)

    collected_events: list[TaskEvent] = []

    def _on_event(event: TaskEvent) -> None:
        """Collect the task event and render it to the console.

        :param event: the emitted task event to record and display.
        """
        collected_events.append(event)
        _render_task_event(event, console)

    captured_flow_id: dict[str, str | None] = {"id": None}

    def _on_started(fid: str) -> None:
        """Capture the flow id and print a start banner.

        :param fid: the flow id assigned when the run begins.
        """
        captured_flow_id["id"] = fid
        console.print(_render_orchestration_msg(f'starting flow {fid}'))

    def _on_task_starting(task_name: str, tool: str) -> None:
        """Announce that a task is about to run.

        :param task_name: name of the task starting.
        :param tool: tool identifier used to execute the task.
        """
        console.print(_render_orchestration_msg(f'running task "{task_name}" [{tool}]'))

    console.print(_render_orchestration_msg(f'loading conduit "{conduit_name}"'))

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(
                conduit_name,
                inputs,
                on_task_event=_on_event,
                on_flow_started=_on_started,
                on_task_starting=_on_task_starting,
                show_steps=show_steps,
            )
        )
    except Exception as e:  # noqa: BLE001
        _render_run_footer(collected_events, console)
        console.print(f"[red]flow failed:[/red] {e}")
        fid = captured_flow_id["id"]
        if fid:
            console.print(f"[red]flow_id:[/red] {fid}")
            console.print(f"[dim]→ atelier status {fid}[/dim]")
        raise typer.Exit(code=1)
    _render_run_footer(collected_events, console)
    console.print(f"[green]flow_id:[/green] {flow_id}")
