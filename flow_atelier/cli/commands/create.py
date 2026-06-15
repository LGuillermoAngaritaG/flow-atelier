"""`atelier create` command — scaffold a new conduit ready to edit."""
from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.markup import escape

from flow_atelier.cli._shared import console
from flow_atelier.cli.main import app
from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.api import CreateConduitInput


@app.command("create", help="Scaffold a new conduit ready to edit.")
def create_cmd(
    name: str = typer.Argument(..., help="Name for the new conduit."),
    description: str = typer.Option(
        None, "--description", "-d", help="Conduit description."
    ),
) -> None:
    """Write a minimal valid starter conduit and print how to run it.

    :param name: name of the conduit to create (folder + ``name:`` field).
    :param description: optional description; a generic default is used if omitted.
    """
    try:
        payload = CreateConduitInput(
            name=name,
            description=description or f"{name} conduit",
            inputs={"name": "Who to greet"},
            tasks=[
                {
                    "name": "greet",
                    "description": "greet someone",
                    "task": "echo hello {{inputs.name}}",
                    "tool": "tool:bash",
                }
            ],
        )
    except (ValidationError, ValueError) as exc:
        console.print(f"[red]invalid conduit:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1)

    try:
        Atelier().create_conduit(payload)
    except FileExistsError:
        console.print(f"[red]conduit already exists:[/red] {escape(name)}")
        raise typer.Exit(code=1)

    console.print(
        f"[green]created[/green] conduits/{escape(name)}/conduit.yaml\n"
        f"[dim]→ run it with: atelier run {escape(name)} --input name=world[/dim]"
    )
