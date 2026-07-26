"""Tests for the backstop on how much task output one panel will print.

Output is printed in full — it is the product of the run, and the reader may
be an agent that cannot go and fetch what an ellipsis dropped. But the
producer is unbounded: `BashExecutor` accumulates stdout with no cap, so a
runaway task would otherwise wedge the terminal.
"""
from __future__ import annotations

import io

from rich.console import Console

from flow_atelier.cli.rendering.render import (
    PANEL_MAX_CHARS,
    _build_failure_body,
    render_task_event,
)
from flow_atelier.schemas.log import TaskEvent
from flow_atelier.schemas.progress import TaskStatus


def _console() -> tuple[Console, io.StringIO]:
    """Build a Rich console writing to an in-memory buffer.

    :returns: tuple of the console and its backing buffer.
    """
    buf = io.StringIO()
    return Console(file=buf, soft_wrap=True, no_color=True, width=200), buf


def _event(**kw) -> TaskEvent:
    """Build a TaskEvent with sane defaults for these tests.

    :param kw: field overrides.
    :returns: the event.
    """
    base = dict(
        task="t",
        tool="tool:bash",
        status=TaskStatus.completed,
        success=True,
        exit_code=0,
        duration_seconds=1.0,
        output="",
        stdout="",
        stderr="",
        iteration=1,
        of=1,
    )
    base.update(kw)
    return TaskEvent(**base)


def test_ordinary_output_is_never_touched() -> None:
    """Verify realistic output passes through byte for byte."""
    body = "\n".join(f"line {i}" for i in range(500))
    assert len(body) < PANEL_MAX_CHARS
    console, buf = _console()
    render_task_event(_event(output=body), console)
    out = buf.getvalue()
    assert "line 0" in out
    assert "line 499" in out
    assert "characters truncated" not in out


def test_runaway_success_output_is_capped() -> None:
    """Verify a runaway producer cannot flood the terminal unbounded."""
    body = "x" * (PANEL_MAX_CHARS + 5_000)
    console, buf = _console()
    render_task_event(_event(output=body), console)
    out = buf.getvalue()
    assert "5000 characters truncated" in out
    assert "atelier logs" in out
    assert len(out) < len(body)


def test_runaway_failure_keeps_the_tail() -> None:
    """Verify the cap keeps the end of a failure, where the diagnostic is."""
    body = "noise\n" * 40_000 + "FATAL: the actual error"
    assert len(body) > PANEL_MAX_CHARS
    rendered = _build_failure_body(body, "")
    assert "FATAL: the actual error" in rendered.plain
    assert "characters truncated" in rendered.plain


def test_both_streams_are_capped_independently() -> None:
    """Verify a huge stdout cannot crowd stderr out of a failure panel."""
    rendered = _build_failure_body("x" * (PANEL_MAX_CHARS + 10), "the real cause")
    assert "the real cause" in rendered.plain
    assert "characters truncated" in rendered.plain
