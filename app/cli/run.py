"""`atelier run` command."""
from __future__ import annotations

import asyncio
import sys

import typer

from app.cli._shared import _parse_inputs, console
from app.cli.main import app
from app.cli.render import _render_run_footer, _render_task_event
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
) -> None:
    """Start a new flow for the named conduit."""
    inputs = _parse_inputs(inputs_raw)
    atelier = Atelier()

    # Prompt for missing inputs when running interactively.
    conduit = atelier.store.read_conduit(conduit_name)
    missing = [k for k in conduit.inputs if k not in inputs]
    if missing and sys.stdin.isatty():
        try:
            for key in missing:
                value = input(f"  {key} ({conduit.inputs[key]}): ")
                inputs[key] = value
        except KeyboardInterrupt:
            print()
            raise typer.Exit(code=130)

    collected_events: list[TaskEvent] = []

    def _on_event(event: TaskEvent) -> None:
        collected_events.append(event)
        _render_task_event(event, console)

    captured_flow_id: dict[str, str | None] = {"id": None}

    def _on_started(fid: str) -> None:
        captured_flow_id["id"] = fid

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(
                conduit_name,
                inputs,
                on_task_event=_on_event,
                on_flow_started=_on_started,
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
