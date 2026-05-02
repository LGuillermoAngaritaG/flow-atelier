"""Typer CLI entrypoint for flow-atelier."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from pathlib import Path

import typer
from rich.table import Table

from app.cli._shared import (
    _flow_duration_seconds,
    _format_clock,
    _format_duration_seconds,
    _parse_inputs,
    _resolve_flow_id,
    _schedule_store,
    console,
)
from app.cli.main import app, list_app, schedule_app, scheduler_app
from app.cli.render import (
    _FLOW_STATUS_STYLE,
    _TASK_STATUS_GLYPHS,
    _build_failure_body,
    _render_log_entry,
    _render_planned_table,
    _render_run_footer,
    _render_task_event,
    _task_status_summary,
    _truncate_tail,
    _truncated_section,
)
from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput
from app.schemas.flow import parse_flow_id
from app.schemas.log import TaskEvent
from app.schemas.progress import FlowStatus, Progress
from app.services.api.app import FastApiServer
from app.services.scheduler import (
    ScheduleStore,
    SchedulerDaemon,
    compute_planned_view,
    default_local_zone,
)

HELLO_CONDUIT_YAML = """name: hello
description: Say hello
inputs:
  name: Who to greet
tasks:
  - greet:
      description: greet someone
      task: "echo hello {{inputs.name}}"
      tool: tool:bash
      depends_on: []
"""


@app.command(
    "init",
    help="Scaffold a local .atelier/ directory with a hello-world conduit.",
)
def init_cmd() -> None:
    """Scaffold ``.atelier/`` with a hello-world conduit; idempotent."""
    atelier_dir = Path.cwd() / ".atelier"
    if atelier_dir.exists():
        console.print("[yellow]atelier is already set up in this project[/yellow]")
        return
    hello_dir = atelier_dir / "conduits" / "hello"
    hello_dir.mkdir(parents=True)
    (hello_dir / "conduit.yaml").write_text(HELLO_CONDUIT_YAML)
    console.print(
        f"[green]initialized[/green] {atelier_dir}\n"
        "try: [bold]atelier run hello --input name=world[/bold]"
    )


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


@app.command("status")
def status_cmd(
    flow_id: str = typer.Argument(..., help="Flow id (or unique prefix) to inspect."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    """Show progress for a flow."""
    atelier = Atelier()
    flow_id = _resolve_flow_id(atelier, flow_id)
    try:
        progress = atelier.get_status(flow_id)
    except FileNotFoundError:
        console.print(f"[red]unknown flow:[/red] {flow_id}")
        raise typer.Exit(code=1)

    if json_mode:
        payload = progress.model_dump(mode="json")
        payload["flow_id"] = flow_id
        payload["duration_seconds"] = _flow_duration_seconds(progress)
        typer.echo(json.dumps(payload, indent=2))
        return

    flow_status_style = _FLOW_STATUS_STYLE.get(progress.status.value, "white")
    duration = _flow_duration_seconds(progress)
    header = (
        f"[bold]flow[/bold] {flow_id}  "
        f"status=[{flow_status_style}]{progress.status.value}[/{flow_status_style}]  "
        f"started={_format_clock(progress.started_at)}  "
        f"duration={_format_duration_seconds(duration)}"
    )
    console.print(header)

    show_iteration = any(tp.of > 1 for tp in progress.tasks.values())
    columns = ["task", "status"]
    if show_iteration:
        columns.append("iteration")
    columns.append("reason")
    table = Table(*columns)
    for name, tp in progress.tasks.items():
        row = [name, tp.status.value]
        if show_iteration:
            row.append(f"{tp.iteration}/{tp.of}" if tp.of > 1 else "")
        row.append(tp.reason or "")
        table.add_row(*row)
    console.print(table)
    console.print(_task_status_summary(progress))


_LOG_SHOW_CHOICES = ("output", "stdout", "stderr", "all")


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
        help="Which channel to print: output | stdout | stderr | all.",
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


@list_app.command("conduits")
def list_conduits_cmd(
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    """List all available conduits (project and global)."""
    atelier = Atelier()
    entries = atelier.store.list_conduits_with_source()

    rows: list[dict[str, object]] = []
    for name, source in entries:
        try:
            conduit = atelier.store.read_conduit(name)
            description = (
                conduit.description.splitlines()[0] if conduit.description else ""
            )
            num_tasks = len(conduit.tasks)
            num_inputs = len(conduit.inputs)
            readable = True
        except Exception:  # noqa: BLE001 — broken yaml shouldn't break list
            description = ""
            num_tasks = -1
            num_inputs = -1
            readable = False
        rows.append(
            {
                "name": name,
                "source": source,
                "description": description,
                "tasks": num_tasks,
                "inputs": num_inputs,
                "readable": readable,
            }
        )

    if json_mode:
        # Drop the internal `readable` key from JSON output for cleanliness.
        typer.echo(
            json.dumps([{k: v for k, v in r.items() if k != "readable"} for r in rows], indent=2)
        )
        return

    if not rows:
        console.print("[yellow]no conduits found[/yellow]")
        return
    table = Table("name", "source", "description", "tasks", "inputs")
    for r in rows:
        source_style = "cyan" if r["source"] == "project" else "magenta"
        if not r["readable"]:
            description_cell = "[red](unreadable)[/red]"
            tasks_cell = "?"
            inputs_cell = "?"
        else:
            description_cell = str(r["description"])
            tasks_cell = str(r["tasks"])
            inputs_cell = str(r["inputs"])
        table.add_row(
            str(r["name"]),
            f"[{source_style}]{r['source']}[/{source_style}]",
            description_cell,
            tasks_cell,
            inputs_cell,
        )
    console.print(table)


@list_app.command("flows")
def list_flows_cmd(
    conduit: str | None = typer.Option(None, "--conduit", "-c"),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    """List all flows, optionally filtered by conduit."""
    atelier = Atelier()
    flows = atelier.list_flows(conduit)

    rows: list[dict[str, object]] = []
    progresses: dict[str, Progress | None] = {}
    for fid in flows:
        try:
            conduit_name, _uuid, _ts = parse_flow_id(fid)
        except ValueError:
            conduit_name = "?"
        progress: Progress | None
        try:
            progress = atelier.store.read_progress(fid)
        except Exception:  # noqa: BLE001
            progress = None
        progresses[fid] = progress
        if progress is None:
            rows.append(
                {
                    "flow_id": fid,
                    "conduit": conduit_name,
                    "status": None,
                    "started_at": None,
                    "finished_at": None,
                    "duration_seconds": None,
                    "task_counts": {},
                }
            )
            continue
        counts: Counter[str] = Counter(
            tp.status.value for tp in progress.tasks.values()
        )
        rows.append(
            {
                "flow_id": fid,
                "conduit": conduit_name,
                "status": progress.status.value,
                "started_at": progress.started_at,
                "finished_at": progress.finished_at,
                "duration_seconds": _flow_duration_seconds(progress),
                "task_counts": dict(counts),
            }
        )

    if json_mode:
        typer.echo(json.dumps(rows, indent=2))
        return

    if not rows:
        console.print("[yellow]no flows found[/yellow]")
        return

    table = Table()
    # flow_id must not be ellipsised: users need to copy it whole.
    table.add_column("flow_id", overflow="fold", no_wrap=False)
    for col in ("conduit", "status", "started", "duration", "tasks"):
        table.add_column(col)
    for r in rows:
        progress = progresses[str(r["flow_id"])]
        if progress is None:
            table.add_row(str(r["flow_id"]), str(r["conduit"]), "[red]?[/red]", "—", "—", "—")
            continue
        status_style = _FLOW_STATUS_STYLE.get(progress.status.value, "white")
        table.add_row(
            str(r["flow_id"]),
            str(r["conduit"]),
            f"[{status_style}]{progress.status.value}[/{status_style}]",
            _format_clock(progress.started_at),
            _format_duration_seconds(_flow_duration_seconds(progress)),
            _task_status_summary(progress),
        )
    console.print(table)


# ---------------------------------------------------------------- schedule / scheduler


def _resolve_schedule(store: ScheduleStore, ref: str):
    """Find a schedule by id, then fall back to a name lookup."""
    job = store.get(ref)
    if job is not None:
        return job
    return store.get_by_name(ref)


def _load_schedule_payload(path: Path) -> CreateScheduleInput:
    """Load YAML or JSON containing a CreateScheduleInput shape."""
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
    help="Install a schedule (JSON or YAML) into .atelier/schedules.json.",
)
def schedule_add_cmd(
    file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True,
        help="Path to a schedule JSON or YAML file."
    ),
) -> None:
    """Validate and persist a schedule via the JSON store."""
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
        collected_events.append(event)
        _render_task_event(event, console)

    captured: dict[str, str | None] = {"id": None}

    def _on_started(fid: str) -> None:
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


@scheduler_app.command(
    "start",
    help="Run the scheduler daemon in the foreground (Ctrl+C / SIGTERM to stop).",
)
def scheduler_start_cmd(
    reload_interval: float = typer.Option(
        30.0, "--reload-interval",
        help="Seconds between schedule store rescans."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level",
        help="Logging level for the daemon (DEBUG, INFO, WARNING, ERROR)."
    ),
) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )
    store = _schedule_store()
    daemon = SchedulerDaemon(
        store,
        default_zone=default_local_zone(),
        default_working_dir=Path.cwd(),
        reload_interval_seconds=reload_interval,
    )
    console.print(
        f"[green]scheduler running[/green] "
        f"(tz={daemon.default_zone}, reload={reload_interval}s, "
        f"schedules={store.schedules_path})"
    )
    try:
        asyncio.run(daemon.run_forever())
    except KeyboardInterrupt:
        pass
    console.print("[dim]scheduler stopped[/dim]")


@scheduler_app.command(
    "status",
    help="Show registered schedules and their next fire times (no daemon required).",
)
def scheduler_status_cmd(
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    schedule_list_cmd(json_mode=json_mode)


# ---------------------------------------------------------------- serve


@app.command(
    "serve",
    help="Run the FastAPI HTTP + WebSocket server with the embedded scheduler.",
)
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(
        8000, "--port", help="Bind port (use 0 for an ephemeral port)."
    ),
    reload_interval: float = typer.Option(
        30.0, "--reload-interval",
        help="Seconds between schedule store rescans."
    ),
    cors_origin: list[str] = typer.Option(
        [], "--cors-origin",
        help="Allowed CORS origin (repeatable). Default = '*'."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level",
        help="Logging level for the server."
    ),
) -> None:
    import uvicorn
    from contextlib import asynccontextmanager

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )

    atelier = Atelier()
    daemon = SchedulerDaemon(
        atelier.schedule_store,
        default_zone=default_local_zone(),
        default_working_dir=Path.cwd(),
        reload_interval_seconds=reload_interval,
    )
    # The schedules POST/DELETE handlers look here to opportunistically
    # re-sync the daemon when a schedule is created or removed.
    atelier.scheduler_daemon = daemon  # type: ignore[attr-defined]

    @asynccontextmanager
    async def _lifespan(app):
        await daemon.start()
        try:
            yield
        finally:
            await daemon.stop()

    cors = list(cors_origin) if cors_origin else None
    api_app = FastApiServer().create_app(atelier, cors_origins=cors)
    api_app.router.lifespan_context = _lifespan

    config = uvicorn.Config(
        api_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        lifespan="on",
    )
    server = uvicorn.Server(config)

    async def _run() -> None:
        serve_task = asyncio.create_task(server.serve())
        # Wait for uvicorn to bind so we can print the actual port.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10.0
        while not server.started and loop.time() < deadline:
            await asyncio.sleep(0.05)
        actual = port
        try:
            if server.servers:
                actual = server.servers[0].sockets[0].getsockname()[1]
        except (AttributeError, IndexError, OSError):
            pass
        console.print(
            f"[green]atelier serve[/green] running at "
            f"[bold]http://{host}:{actual}[/bold]"
        )
        await serve_task

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    app()
