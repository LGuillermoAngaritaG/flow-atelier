"""`atelier scheduler` sub-app commands."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer

from app.cli._shared import _schedule_store, console
from app.cli.main import scheduler_app
from app.cli.commands.schedule import schedule_list_cmd
from app.services.scheduler import SchedulerDaemon, default_local_zone


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
    """Run the scheduler daemon in the foreground until interrupted.

    :param reload_interval: seconds between schedule store rescans.
    :param log_level: logging level for the daemon (DEBUG/INFO/WARNING/ERROR).
    """
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
        f"schedules={store.schedules_dir})"
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
    """Show registered schedules and their next fire times.

    :param json_mode: when true, emit machine-readable JSON instead of a table.
    """
    schedule_list_cmd(json_mode=json_mode)
