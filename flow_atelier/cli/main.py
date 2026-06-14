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


def _version_callback(value: bool) -> None:
    """Print the installed version and exit when ``--version`` is passed.

    :param value: ``True`` when the flag is present.
    """
    if value:
        from flow_atelier import __version__

        typer.echo(f"flow-atelier {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the flow-atelier version and exit.",
    ),
) -> None:
    """Root callback hosting global options.

    :param version: eager flag handled by :func:`_version_callback`.
    """
    from flow_atelier.cli.updater import start_background_update_check

    start_background_update_check()


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
from flow_atelier.cli.commands import (  # noqa: E402, F401
    check,
    init,
    logs,
    outputs,
    plan,
    rm,
    run,
    schedule,
    scheduler,
    serve,
    status,
    stop,
)
from flow_atelier.cli.commands import list as _list  # noqa: E402, F401
