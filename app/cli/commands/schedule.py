"""`atelier schedule` sub-app commands."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from app.cli._shared import _schedule_store, console
from app.cli.main import schedule_app
from app.cli.rendering.render import _render_planned_table, _render_run_footer, _render_task_event
from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput
from app.schemas.log import TaskEvent
from app.services.scheduler import (
    ScheduleStore,
    compute_planned_view,
    default_local_zone,
)


def _resolve_schedule(store: ScheduleStore, ref: str):
    """Find a schedule by id, then fall back to a name lookup.

    :param store: schedule store to query.
    :param ref: schedule id or ``schedule.name`` value.
    :returns: the matched schedule, or None when nothing matches.
    """
    job = store.get(ref)
    if job is not None:
        return job
    return store.get_by_name(ref)


def _load_schedule_payload(path: Path) -> CreateScheduleInput:
    """Load YAML or JSON containing a CreateScheduleInput shape.

    :param path: filesystem path to a JSON or YAML schedule file.
    :returns: a validated :class:`CreateScheduleInput`.
    """
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(text)
    else:
        import yaml

        raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("schedule file must contain a JSON/YAML mapping")
    return CreateScheduleInput.model_validate(raw)


@schedule_app.command(
    "add",
    help="Install a schedule (JSON or YAML) into .atelier/schedules/.",
)
def schedule_add_cmd(
    file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True,
        help="Path to a schedule JSON or YAML file."
    ),
) -> None:
    """Validate and persist a schedule via the JSON store.

    :param file: path to a schedule JSON or YAML file to install.
    """
    store = _schedule_store()
    try:
        payload = _load_schedule_payload(file)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]invalid schedule:[/red] {e}")
        raise typer.Exit(code=1)
    job = store.create(payload)
    console.print(f"[green]installed[/green] {job.id}")


@schedule_app.command("list", help="List installed schedules and their next fire times.")
def schedule_list_cmd(
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    """List installed schedules and their next fire times.

    :param json_mode: when true, emit machine-readable JSON instead of a table.
    """
    store = _schedule_store()
    planned = compute_planned_view(
        store,
        default_zone=default_local_zone(),
        default_working_dir=Path.cwd(),
    )

    if json_mode:
        payload = {
            "schedules": [
                {
                    "id": p.id,
                    "name": p.name,
                    "conduit": p.conduit_name,
                    "kind": p.schedule_kind,
                    "next_fire_time": (
                        p.next_fire_time.isoformat() if p.next_fire_time else None
                    ),
                    "working_dir": str(p.working_dir),
                }
                for p in planned
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    if not planned:
        console.print("[yellow]no schedules found[/yellow]")
        return

    console.print(_render_planned_table(planned))


@schedule_app.command("remove", help="Soft-delete a schedule by id or name.")
def schedule_remove_cmd(
    ref: str = typer.Argument(..., help="Schedule id or schedule.name."),
) -> None:
    """Soft-delete a schedule by id or name.

    :param ref: schedule id or ``schedule.name`` to remove.
    """
    store = _schedule_store()
    job = _resolve_schedule(store, ref)
    if job is None:
        console.print(f"[yellow]schedule not found:[/yellow] {ref}")
        raise typer.Exit(code=1)
    store.delete(job.id)
    console.print(f"[green]removed[/green] {job.id}")


@schedule_app.command(
    "run-now",
    help="Run a scheduled conduit immediately (bypasses the daemon).",
)
def schedule_run_now_cmd(
    ref: str = typer.Argument(..., help="Schedule id or schedule.name."),
) -> None:
    """Run a scheduled conduit immediately, bypassing the daemon.

    :param ref: schedule id or ``schedule.name`` to execute now.
    """
    store = _schedule_store()
    job = _resolve_schedule(store, ref)
    if job is None:
        console.print(f"[red]schedule not found:[/red] {ref}")
        raise typer.Exit(code=1)

    working_dir = Path.cwd()
    if job.run_path:
        wd = Path(job.run_path)
        working_dir = wd if wd.is_absolute() else (working_dir / wd).resolve()

    atelier = Atelier(base_dir=working_dir / ".atelier")
    collected_events: list[TaskEvent] = []

    def _on_event(event: TaskEvent) -> None:
        """Collect the task event and render it to the console.

        :param event: the emitted task event to record and display.
        """
        collected_events.append(event)
        _render_task_event(event, console)

    captured: dict[str, str | None] = {"id": None}

    def _on_started(fid: str) -> None:
        """Capture the flow id once the run begins.

        :param fid: the flow id assigned when the run starts.
        """
        captured["id"] = fid

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(
                job.conduit_name,
                dict(job.inputs),
                on_task_event=_on_event,
                on_flow_started=_on_started,
            )
        )
    except Exception as e:  # noqa: BLE001
        _render_run_footer(collected_events, console)
        console.print(f"[red]flow failed:[/red] {e}")
        if captured["id"]:
            console.print(f"[red]flow_id:[/red] {captured['id']}")
        raise typer.Exit(code=1)
    _render_run_footer(collected_events, console)
    console.print(f"[green]flow_id:[/green] {flow_id}")
