"""`atelier logs` command (and `--follow` loop)."""
from __future__ import annotations

import json
import time

import typer

from app.cli._shared import _resolve_flow_id, console
from app.cli.main import app
from app.cli.render import _render_log_entry
from app.core.atelier import Atelier
from app.schemas.progress import FlowStatus

_LOG_SHOW_CHOICES = ("output", "stdout", "stderr", "steps", "all")


@app.command(
    "logs",
    help="Show recorded stdout/stderr/output for each task in a flow.",
)
def logs_cmd(
    flow_id: str = typer.Argument(..., help="Flow id (or unique prefix) to inspect."),
    task: str | None = typer.Option(
        None, "--task", "-t", help="Show only entries for this task."
    ),
    show: str = typer.Option(
        "output",
        "--show",
        "-s",
        help="Which channel to print: output | stdout | stderr | steps | all.",
    ),
    last: int | None = typer.Option(
        None, "--last", "-n", help="Show only the last N entries."
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Tail mode: print existing entries, then poll for new ones until the flow finishes.",
    ),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of panels."
    ),
) -> None:
    """Show recorded stdout/stderr/output for each task iteration in a flow."""
    if show not in _LOG_SHOW_CHOICES:
        console.print(
            f"[red]invalid --show value:[/red] {show}  "
            f"(allowed: {', '.join(_LOG_SHOW_CHOICES)})"
        )
        raise typer.Exit(code=2)
    if follow and json_mode:
        console.print("[red]--follow and --json are mutually exclusive[/red]")
        raise typer.Exit(code=2)
    if follow and last is not None:
        console.print("[red]--follow and --last are mutually exclusive[/red]")
        raise typer.Exit(code=2)

    atelier = Atelier()
    flow_id = _resolve_flow_id(atelier, flow_id)

    if follow:
        _follow_logs(atelier, flow_id, task, show)
        return

    try:
        entries = atelier.store.read_logs(flow_id)
    except FileNotFoundError:
        console.print(f"[red]unknown flow:[/red] {flow_id}")
        raise typer.Exit(code=1)

    if task is not None:
        entries = [e for e in entries if e.task == task]

    if not entries:
        scope = f"task {task!r}" if task else "this flow"
        if json_mode:
            typer.echo("[]")
            raise typer.Exit(code=1)
        console.print(f"[yellow]no log entries for {scope}[/yellow]")
        raise typer.Exit(code=1)

    if last is not None and last > 0:
        entries = entries[-last:]

    if json_mode:
        typer.echo(
            json.dumps([e.model_dump(mode="json") for e in entries], indent=2)
        )
        return

    for entry in entries:
        _render_log_entry(entry, show, console)


def _follow_logs(
    atelier: Atelier,
    flow_id: str,
    task: str | None,
    show: str,
    poll_seconds: float = 0.25,
) -> None:
    """Render existing entries, then poll for new ones until the flow ends.

    Exits cleanly when the flow's progress.json reports a terminal status
    (``completed`` or ``failed``). Exits 130 on KeyboardInterrupt.
    """
    rendered = 0

    def _read() -> list:
        try:
            entries = atelier.store.read_logs(flow_id)
        except FileNotFoundError:
            console.print(f"[red]unknown flow:[/red] {flow_id}")
            raise typer.Exit(code=1)
        if task is not None:
            entries = [e for e in entries if e.task == task]
        return entries

    def _drain_and_render() -> None:
        nonlocal rendered
        entries = _read()
        for entry in entries[rendered:]:
            _render_log_entry(entry, show, console)
        rendered = len(entries)

    try:
        while True:
            _drain_and_render()
            try:
                progress = atelier.store.read_progress(flow_id)
            except FileNotFoundError:
                # Flow vanished mid-stream; nothing more to do.
                return
            if progress.status != FlowStatus.running:
                # Final pass to capture any entries written between the last
                # read and the terminal state transition.
                _drain_and_render()
                return
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        console.print("[dim]— follow interrupted —[/dim]")
        raise typer.Exit(code=130)
