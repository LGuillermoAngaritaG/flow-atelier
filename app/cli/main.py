"""Root Typer entry point — constructs ``app`` and the three sub-apps,
then imports each command module for its side-effect decorations.
"""
from __future__ import annotations

import typer

app = typer.Typer(
    help="flow-atelier: run reproducible async DAG workflows (conduits).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
list_app = typer.Typer(
    help="List conduits or flows.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(list_app, name="list")

schedule_app = typer.Typer(
    help="Manage scheduled conduit runs (.atelier/schedules/).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(schedule_app, name="schedule")

scheduler_app = typer.Typer(
    help="Run and inspect the scheduler daemon.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(scheduler_app, name="scheduler")

# Side-effect imports: each command module decorates its handler against
# the appropriate Typer instance above. Order matches the original
# decoration order in app/main.py so --help layout stays byte-identical.
from app.cli.commands import (  # noqa: E402, F401
    init,
    run,
    status,
    logs,
    list as _list,
    schedule,
    scheduler,
    serve,
)
