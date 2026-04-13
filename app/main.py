"""Typer CLI entrypoint for flow-atelier."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.core.atelier import Atelier
from app.schemas.log import TaskEvent

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

app = typer.Typer(
    help="flow-atelier: run reproducible async DAG workflows (conduits).",
    no_args_is_help=True,
)
list_app = typer.Typer(help="List conduits or flows.", no_args_is_help=True)
app.add_typer(list_app, name="list")

console = Console()


@app.command("init")
def init_cmd() -> None:
    """Scaffold a local ``.atelier/`` with a hello-world conduit.

    If ``.atelier/`` already exists in the current directory, prints a
    message and exits 0 without touching anything.
    """
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


def _parse_inputs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            raise typer.BadParameter(f"--input expects key=value, got {p!r}")
        key, value = p.split("=", 1)
        out[key] = value
    return out


def _truncate_tail(text: str, max_lines: int = 20) -> tuple[str, int]:
    """Return ``(displayed_text, dropped_line_count)``.

    Keeps only the last ``max_lines`` lines of ``text``. If the input has
    ``max_lines`` or fewer lines, returns it unchanged with a dropped count
    of zero. Preserves a trailing newline character only when meaningful
    (i.e. never).

    :param text: raw text to truncate from the top
    :param max_lines: maximum number of trailing lines to keep
    :returns: tuple of the retained text and how many lines were dropped
    """
    if not text:
        return "", 0
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines), 0
    dropped = len(lines) - max_lines
    return "\n".join(lines[-max_lines:]), dropped


def _render_task_event(event: TaskEvent, console: Console) -> None:
    """Pretty-print a :class:`TaskEvent` to ``console``.

    Success with non-empty output → green-bordered :class:`Panel`.
    Failure → red-bordered panel, preferring ``output`` and falling back
    to ``stderr``.
    Success with empty output → compact single-line summary (no panel)
    to avoid visual noise for echo-style tasks.

    Long bodies are truncated to the last 20 lines with a dim
    ``… (N lines truncated)`` header so the terminal stays readable.
    """
    iter_suffix = f" ({event.iteration}/{event.of})" if event.of > 1 else ""
    title_core = f"{event.task} [{event.tool}]{iter_suffix}"
    subtitle = f"exit={event.exit_code} · {event.duration_seconds}s"

    if event.success:
        body_source = event.output
        border_style = "green"
        title = Text(f"✓ {title_core}", style="bold green")
    else:
        body_source = event.output or event.stderr
        border_style = "red"
        title = Text(f"✗ {title_core}", style="bold red")

    # Compact single-line path: successful task with nothing to show.
    if event.success and not body_source.strip():
        console.print(
            f"[green]✓[/green] [bold]{event.task}[/bold] "
            f"[dim]\\[{event.tool}]{iter_suffix}[/dim]  "
            f"[dim]{subtitle}  (no output)[/dim]"
        )
        return

    displayed, dropped = _truncate_tail(body_source, max_lines=20)
    if dropped:
        body_text = Text()
        body_text.append(f"… ({dropped} lines truncated)\n", style="dim italic")
        body_text.append(displayed)
    else:
        body_text = Text(displayed or "(empty)")

    console.print(
        Panel(
            body_text,
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            border_style=border_style,
            padding=(0, 1),
        )
    )


@app.command("run")
def run_cmd(
    conduit_name: str = typer.Argument(..., help="Name of the conduit to run."),
    inputs_raw: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        help="key=value input (repeatable).",
    ),
) -> None:
    """Start a new flow for ``conduit_name``.

    :param conduit_name: name of the conduit to run
    :param inputs_raw: list of ``key=value`` input strings
    :returns: None
    """
    inputs = _parse_inputs(inputs_raw)
    atelier = Atelier()

    def _on_event(event: TaskEvent) -> None:
        _render_task_event(event, console)

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(conduit_name, inputs, on_task_event=_on_event)
        )
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]flow failed:[/red] {e}")
        raise typer.Exit(code=1)
    console.print(f"[green]flow_id:[/green] {flow_id}")


@app.command("status")
def status_cmd(flow_id: str = typer.Argument(..., help="Flow id to inspect.")) -> None:
    """Show live progress for a flow."""
    atelier = Atelier()
    try:
        progress = atelier.get_status(flow_id)
    except FileNotFoundError:
        console.print(f"[red]unknown flow:[/red] {flow_id}")
        raise typer.Exit(code=1)

    console.print(f"[bold]flow[/bold] {flow_id}  status={progress.status.value}")
    table = Table("task", "status", "iteration", "reason")
    for name, tp in progress.tasks.items():
        table.add_row(
            name,
            tp.status.value,
            f"{tp.iteration}/{tp.of}" if tp.of > 1 else "",
            tp.reason or "",
        )
    console.print(table)


@list_app.command("conduits")
def list_conduits_cmd() -> None:
    """List all available conduits (project and global)."""
    atelier = Atelier()
    entries = atelier.store.list_conduits_with_source()
    if not entries:
        console.print("[yellow]no conduits found[/yellow]")
        return
    for name, source in entries:
        tag_color = "cyan" if source == "project" else "magenta"
        console.print(
            f"- {name} [{tag_color}]\\[{source}][/{tag_color}]"
        )


@list_app.command("flows")
def list_flows_cmd(
    conduit: str | None = typer.Option(None, "--conduit", "-c"),
) -> None:
    """List all flows, optionally filtered by conduit."""
    atelier = Atelier()
    flows = atelier.list_flows(conduit)
    if not flows:
        console.print("[yellow]no flows found[/yellow]")
        return
    for fid in flows:
        console.print(f"- {fid}")


if __name__ == "__main__":
    app()
