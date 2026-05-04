"""Rich rendering helpers for the CLI presentation layer."""
from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.cli._shared import _format_duration_seconds, _format_clock, _format_next_fire
from app.schemas.log import IntermediateStep, StepKind, TaskEvent
from app.schemas.progress import FlowStatus, Progress, TaskStatus
from app.services.scheduler import PlannedJob


def _render_step(step: IntermediateStep) -> Text:
    """Render a single intermediate step as a compact Rich Text line.

    - Thinking: ``  💭 {text[:120]}...`` dim italic
    - Tool call: ``  🔧 {tool_name}  {location}`` bold dim + dim
    - Tool result: ``     ✓ status`` or ``     ✗ status`` green/red
    """
    t = Text()
    if step.kind == StepKind.thinking:
        truncated = step.text[:120] + ("..." if len(step.text) > 120 else "")
        t.append("  💭 ", style="dim italic")
        t.append(truncated, style="dim italic")
    elif step.kind == StepKind.tool_call:
        loc = f"  {step.locations[0]}" if step.locations else ""
        t.append("  🔧 ", style="dim")
        t.append(step.tool_name, style="bold dim")
        if loc:
            t.append(loc, style="dim")
    elif step.kind == StepKind.tool_result:
        if step.tool_status == "failed":
            t.append("     ✗ ", style="red")
            t.append(step.tool_status, style="red")
        else:
            t.append("     ✓ ", style="green")
            t.append(step.tool_status, style="green")
    return t


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


def _step_summary_line(steps: list[IntermediateStep]) -> str | None:
    """Return a dim summary like ``thinking(3) tools(7)`` or None if empty."""
    if not steps:
        return None
    thinking = sum(1 for s in steps if s.kind == StepKind.thinking)
    tools = sum(1 for s in steps if s.kind in (StepKind.tool_call, StepKind.tool_result))
    parts = []
    if thinking:
        parts.append(f"thinking({thinking})")
    if tools:
        parts.append(f"tools({tools})")
    return " ".join(parts) if parts else None


def _render_steps_timeline(steps: list[IntermediateStep]) -> Text:
    """Render each step as a compact timestamped line."""
    body = Text()
    for step in steps:
        ts = _format_clock(step.timestamp)
        if step.kind == StepKind.thinking:
            body.append(f"[{ts}] ", style="dim")
            body.append("[thinking] ", style="dim bold")
            body.append(f"{step.text[:120]}\n", style="dim")
        elif step.kind == StepKind.tool_call:
            loc = f" {step.locations[0]}" if step.locations else ""
            body.append(f"[{ts}] ", style="dim")
            body.append("[tool] ", style="dim bold")
            body.append(f"{step.tool_name}{loc}\n")
        elif step.kind == StepKind.tool_result:
            body.append(f"[{ts}] ", style="dim")
            body.append(f"  -> {step.tool_status}\n")
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
        summary = _step_summary_line(event.steps)
        body_text = Text()
        if summary:
            body_text.append(f"{summary}\n", style="dim")
        body_text.append(_truncated_section(body_source))
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

    if show == "steps":
        steps = getattr(entry, "steps", [])
        if steps:
            body = _render_steps_timeline(steps)
        else:
            body = Text("(no steps)")
    elif show == "all":
        body = Text()
        steps = getattr(entry, "steps", [])
        if steps:
            body.append(_render_steps_timeline(steps))
            body.append("\n")
        if entry.stdout:
            body.append("stdout:\n", style="dim bold")
            body.append(entry.stdout)
            if entry.stderr:
                body.append("\n\n")
        if entry.stderr:
            body.append("stderr:\n", style="bold red")
            body.append(entry.stderr)
        if not steps and not entry.stdout and not entry.stderr:
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


def _render_planned_table(planned: list[PlannedJob]) -> Table:
    table = Table("id", "name", "conduit", "kind", "next fire", "working_dir")
    for p in planned:
        kind_style = "cyan" if p.schedule_kind == "recurring" else "magenta"
        next_cell = _format_next_fire(p.next_fire_time)
        if p.next_fire_time is None and p.schedule_kind == "once":
            next_cell = "[dim](already fired)[/dim]"
        table.add_row(
            p.id,
            p.name,
            p.conduit_name,
            f"[{kind_style}]{p.schedule_kind}[/{kind_style}]",
            next_cell,
            str(p.working_dir),
        )
    return table
