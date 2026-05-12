"""`atelier init` command."""
from __future__ import annotations

from pathlib import Path

from app.cli._shared import console
from app.cli.main import app

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
