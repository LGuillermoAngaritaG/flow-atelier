"""Typer CLI entrypoint for flow-atelier."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.core.atelier import Atelier
from app.core.settings import AtelierSettings
from app.schemas.flow import parse_flow_id
from app.schemas.log import TaskEvent
from app.schemas.progress import FlowStatus, Progress, TaskStatus
from app.services.scheduler import (
    PlannedJob,
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
    help="Manage scheduled conduit runs (YAML files in .atelier/schedules/).",
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

console = Console()


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


def _truncated_section(text: str, max_lines: int = 20) -> Text:
    """Truncate ``text`` to its last ``max_lines`` lines and return a
    Rich :class:`Text` with an italic-dim header noting the dropped count.
    """
    displayed, dropped = _truncate_tail(text, max_lines=max_lines)
    body = Text()
    if dropped:
        body.append(f"… ({dropped} lines truncated)\n", style="dim italic")
    body.append(displayed)
    return body


def _build_failure_body(stdout: str, stderr: str) -> Text:
    """Render a failure body that always surfaces stderr.

    - Both empty → ``(empty)``.
    - Only one populated → the existing single-body (truncated) form.
    - Both populated → labelled sections so the diagnostic stderr is
      visible alongside the stdout context.
    """
    has_stdout = bool(stdout)
    has_stderr = bool(stderr)
    if not has_stdout and not has_stderr:
        return Text("(empty)")
    if has_stdout and not has_stderr:
        return _truncated_section(stdout)
    if has_stderr and not has_stdout:
        return _truncated_section(stderr)
    body = Text()
    body.append("stdout:\n", style="dim bold")
    body.append(_truncated_section(stdout))
    body.append("\n\n")
    body.append("stderr:\n", style="bold red")
    body.append(_truncated_section(stderr))
    return body


def _render_task_event(event: TaskEvent, console: Console) -> None:
    """Pretty-print a :class:`TaskEvent` to ``console``.

    Success with non-empty output → green-bordered :class:`Panel`.
    Failure → red-bordered panel showing stdout *and* stderr when both
    are populated (stderr is the primary diagnostic and used to be
    hidden whenever stdout had any content).
    Success with empty output → compact single-line summary (no panel)
    to avoid visual noise for echo-style tasks.

    Long bodies are truncated to the last 20 lines with a dim
    ``… (N lines truncated)`` header so the terminal stays readable.
    """
    iter_suffix = f" ({event.iteration}/{event.of})" if event.of > 1 else ""
    title_core = f"{event.task} [{event.tool}]{iter_suffix}"
    subtitle = f"exit={event.exit_code} · {event.duration_seconds}s"

    # Compact one-liners for non-running dispositions — these never had
    # a real iteration so a full panel of "(empty)" output is misleading.
    if event.status == TaskStatus.skipped:
        reason = f"  [dim italic]({event.reason})[/dim italic]" if event.reason else ""
        console.print(
            f"[yellow]⏭[/yellow] [bold]{event.task}[/bold] "
            f"[dim]\\[{event.tool}]{iter_suffix}[/dim]  "
            f"[yellow]skipped[/yellow]{reason}"
        )
        return
    if event.status == TaskStatus.cancelled:
        reason = f"  [dim italic]({event.reason})[/dim italic]" if event.reason else ""
        console.print(
            f"[red]⊘[/red] [bold]{event.task}[/bold] "
            f"[dim]\\[{event.tool}]{iter_suffix}[/dim]  "
            f"[red]cancelled[/red]{reason}"
        )
        return

    if event.success:
        border_style = "green"
        title = Text(f"✓ {title_core}", style="bold green")
        body_source = event.output
        # Compact single-line path: successful task with nothing to show.
        if not body_source.strip():
            console.print(
                f"[green]✓[/green] [bold]{event.task}[/bold] "
                f"[dim]\\[{event.tool}]{iter_suffix}[/dim]  "
                f"[dim]{subtitle}  (no output)[/dim]"
            )
            return
        # Interactive harness tasks already streamed their full
        # transcript live (incl. multi-turn user replies), so a body
        # panel here would just duplicate what scrolled by. Show a
        # compact single-line summary instead.
        if event.live_streamed:
            console.print(
                f"[green]✓[/green] [bold]{event.task}[/bold] "
                f"[dim]\\[{event.tool}]{iter_suffix}[/dim]  "
                f"[dim]{subtitle}  (streamed live above)[/dim]"
            )
            return
        body_text = _truncated_section(body_source)
    else:
        border_style = "red"
        title = Text(f"✗ {title_core}", style="bold red")
        body_text = _build_failure_body(event.output or event.stdout, event.stderr)

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


_FLOW_STATUS_STYLE: dict[str, str] = {
    FlowStatus.completed.value: "green",
    FlowStatus.failed.value: "red",
    FlowStatus.running.value: "yellow",
}

_TASK_STATUS_GLYPHS: list[tuple[TaskStatus, str, str]] = [
    (TaskStatus.completed, "✓", "green"),
    (TaskStatus.failed, "✗", "red"),
    (TaskStatus.skipped, "⏭", "yellow"),
    (TaskStatus.cancelled, "⊘", "red"),
    (TaskStatus.running, "⏳", "yellow"),
    (TaskStatus.pending, "·", "dim"),
]


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Engine emits Z-suffixed ISO; fromisoformat handles +00:00 form.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_duration_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds:.2f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _flow_duration_seconds(progress: Progress) -> float | None:
    start = _parse_iso(progress.started_at)
    end = _parse_iso(progress.finished_at) if progress.finished_at else None
    if start is None:
        return None
    if end is None:
        # In-flight: don't try to compute against wall-clock here — just omit.
        return None
    return (end - start).total_seconds()


def _format_clock(ts: str | None) -> str:
    dt = _parse_iso(ts)
    if dt is None:
        return "—"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _task_status_summary(progress: Progress) -> Text:
    """Render `✓3 ✗1 ⏭2 ⊘0 ⏳1` with only non-zero entries."""
    counts: Counter[TaskStatus] = Counter(
        tp.status for tp in progress.tasks.values()
    )
    text = Text()
    first = True
    for status, glyph, style in _TASK_STATUS_GLYPHS:
        n = counts.get(status, 0)
        if n == 0:
            continue
        if not first:
            text.append("  ")
        text.append(f"{glyph}{n}", style=style)
        first = False
    if first:
        text.append("—", style="dim")
    return text


def _render_run_footer(events: list[TaskEvent], console: Console) -> None:
    """One-line aggregate summary printed at the end of `atelier run`."""
    if not events:
        return
    counts: Counter[TaskStatus] = Counter(e.status for e in events)
    total_dur = sum(e.duration_seconds for e in events)
    parts: list[str] = []
    for status, glyph, style in _TASK_STATUS_GLYPHS:
        n = counts.get(status, 0)
        if n == 0:
            continue
        parts.append(f"[{style}]{glyph}{n}[/{style}]")
    summary = "  ".join(parts) if parts else "—"
    console.print(
        f"[dim]{summary}  ·  total {_format_duration_seconds(total_dur)}[/dim]"
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


def _resolve_flow_id(atelier: Atelier, candidate: str) -> str:
    """Resolve ``candidate`` to a full flow id, supporting git-style prefixes.

    - Exact id present on disk → returned as-is.
    - Otherwise scans all known flows. Exactly one prefix match → that id.
    - Zero matches → exits with ``unknown flow`` (code 1).
    - More than one → exits with ``ambiguous flow id`` and lists candidates.
    """
    all_flows = atelier.list_flows()
    if candidate in all_flows:
        return candidate
    matches = [fid for fid in all_flows if fid.startswith(candidate)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        console.print(f"[red]unknown flow:[/red] {candidate}")
        raise typer.Exit(code=1)
    console.print(f"[red]ambiguous flow id:[/red] {candidate} matches:")
    for m in matches[:10]:
        console.print(f"  - {m}")
    if len(matches) > 10:
        console.print(f"  … and {len(matches) - 10} more")
    raise typer.Exit(code=1)


_LOG_SHOW_CHOICES = ("output", "stdout", "stderr", "all")


def _render_log_entry(entry, show: str, console: Console) -> None:
    """Render one LogEntry as a Rich Panel.

    ``show`` controls which body channel is displayed:
    ``output`` (default), ``stdout``, ``stderr``, or ``all`` (both
    labelled when present).
    """
    iter_suffix = f" ({entry.iteration}/{entry.of})" if entry.of > 1 else ""
    title_core = f"{entry.task} [{entry.tool}]{iter_suffix}"
    success = entry.exit_code == 0
    glyph = "✓" if success else "✗"
    border = "green" if success else "red"
    title = Text(f"{glyph} {title_core}", style=f"bold {border}")
    started = _format_clock(entry.started_at)
    subtitle = (
        f"{started}  ·  exit={entry.exit_code}  ·  "
        f"{entry.duration_seconds}s"
    )

    if show == "all":
        body = Text()
        if entry.stdout:
            body.append("stdout:\n", style="dim bold")
            body.append(entry.stdout)
            if entry.stderr:
                body.append("\n\n")
        if entry.stderr:
            body.append("stderr:\n", style="bold red")
            body.append(entry.stderr)
        if not entry.stdout and not entry.stderr:
            body = Text("(empty)")
    else:
        raw = {
            "output": entry.output,
            "stdout": entry.stdout,
            "stderr": entry.stderr,
        }[show]
        body = Text(raw or "(empty)")

    console.print(
        Panel(
            body,
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            border_style=border,
            padding=(0, 1),
        )
    )


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


def _schedule_store() -> ScheduleStore:
    settings = AtelierSettings()
    return ScheduleStore(
        settings.schedules_dir,
        state_path=settings.scheduler_state_path,
    )


def _format_next_fire(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z").strip()


def _render_planned_table(planned: list[PlannedJob]) -> Table:
    table = Table("name", "conduit", "kind", "next fire", "working_dir")
    for p in planned:
        kind_style = "cyan" if p.schedule_kind == "recurring" else "magenta"
        next_cell = _format_next_fire(p.next_fire_time)
        if p.next_fire_time is None and p.schedule_kind == "once":
            next_cell = "[dim](already fired)[/dim]"
        table.add_row(
            p.name,
            p.conduit,
            f"[{kind_style}]{p.schedule_kind}[/{kind_style}]",
            next_cell,
            str(p.working_dir),
        )
    return table


@schedule_app.command(
    "add",
    help="Install a schedule YAML into .atelier/schedules/.",
)
def schedule_add_cmd(
    file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True,
        help="Path to a schedule YAML file."
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite if a schedule with this name already exists."
    ),
) -> None:
    """Validate and copy a schedule YAML into ``.atelier/schedules/``."""
    store = _schedule_store()
    try:
        dest = store.install(file, force=force)
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]  [dim](use --force to overwrite)[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]invalid schedule:[/red] {e}")
        raise typer.Exit(code=1)
    console.print(f"[green]installed[/green] {dest}")


@schedule_app.command("list", help="List installed schedules and their next fire times.")
def schedule_list_cmd(
    json_mode: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
) -> None:
    store = _schedule_store()
    planned, errors = compute_planned_view(
        store,
        default_zone=default_local_zone(),
        default_working_dir=Path.cwd(),
    )

    if json_mode:
        payload = {
            "schedules": [
                {
                    "name": p.name,
                    "conduit": p.conduit,
                    "kind": p.schedule_kind,
                    "next_fire_time": (
                        p.next_fire_time.isoformat() if p.next_fire_time else None
                    ),
                    "working_dir": str(p.working_dir),
                }
                for p in planned
            ],
            "errors": [
                {"path": str(e.source_path), "error": e.error} for e in errors
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    if not planned and not errors:
        console.print("[yellow]no schedules found[/yellow]")
        return

    if planned:
        console.print(_render_planned_table(planned))
    for err in errors:
        console.print(
            f"[red]× {err.source_path.name}:[/red] {err.error}"
        )


@schedule_app.command("remove", help="Delete a schedule YAML from .atelier/schedules/.")
def schedule_remove_cmd(
    name: str = typer.Argument(..., help="Schedule name (filename stem)."),
) -> None:
    store = _schedule_store()
    if not store.remove(name):
        console.print(f"[yellow]schedule not found:[/yellow] {name}")
        raise typer.Exit(code=1)
    console.print(f"[green]removed[/green] {name}")


@schedule_app.command(
    "run-now",
    help="Run a scheduled conduit immediately (bypasses the daemon).",
)
def schedule_run_now_cmd(
    name: str = typer.Argument(..., help="Schedule name to dispatch."),
) -> None:
    store = _schedule_store()
    try:
        definition = store.read(name)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    working_dir = Path.cwd()
    if definition.working_dir is not None:
        wd = Path(definition.working_dir)
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
                definition.conduit,
                dict(definition.inputs),
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
        help="Seconds between YAML directory rescans."
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
        f"schedules_dir={store.schedules_dir})"
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


if __name__ == "__main__":
    app()
