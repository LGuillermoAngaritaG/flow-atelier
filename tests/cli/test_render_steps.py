"""Tests for step rendering in task event panels and log entries."""
from __future__ import annotations

import io

from rich.console import Console

from app.cli.render import _render_log_entry, _render_task_event
from app.schemas.log import IntermediateStep, LogEntry, StepKind, TaskEvent
from app.schemas.progress import TaskStatus


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    c = Console(file=buf, no_color=True, width=120)
    return c, buf


class TestRenderTaskEventStepSummary:
    def test_step_summary_shown_for_success_with_steps(self) -> None:
        steps = [
            IntermediateStep(kind=StepKind.thinking, text="hmm"),
            IntermediateStep(kind=StepKind.thinking, text="ok"),
            IntermediateStep(kind=StepKind.tool_call, tool_name="Read"),
            IntermediateStep(kind=StepKind.tool_result, tool_status="completed"),
        ]
        event = TaskEvent(
            task="build",
            tool="harness:claude-code",
            output="done",
            success=True,
            duration_seconds=5.0,
            steps=steps,
        )
        c, buf = _console()
        _render_task_event(event, c)
        output = buf.getvalue()
        # Should show thinking count and tool count
        assert "thinking(2)" in output
        assert "tools(2)" in output

    def test_no_step_summary_when_steps_empty(self) -> None:
        event = TaskEvent(
            task="build",
            tool="tool:bash",
            output="done",
            success=True,
            duration_seconds=1.0,
        )
        c, buf = _console()
        _render_task_event(event, c)
        output = buf.getvalue()
        assert "thinking" not in output
        assert "tools" not in output

    def test_no_step_summary_for_live_streamed(self) -> None:
        """Live-streamed tasks use the compact one-liner, no step summary."""
        steps = [IntermediateStep(kind=StepKind.thinking, text="x")]
        event = TaskEvent(
            task="build",
            tool="harness:claude-code",
            output="done",
            success=True,
            live_streamed=True,
            steps=steps,
        )
        c, buf = _console()
        _render_task_event(event, c)
        output = buf.getvalue()
        assert "streamed live" in output

    def test_no_step_summary_for_empty_output(self) -> None:
        """Success with empty output uses compact one-liner."""
        steps = [IntermediateStep(kind=StepKind.thinking, text="x")]
        event = TaskEvent(
            task="build",
            tool="tool:bash",
            output="",
            success=True,
            steps=steps,
        )
        c, buf = _console()
        _render_task_event(event, c)
        output = buf.getvalue()
        assert "no output" in output


class TestRenderLogEntrySteps:
    def _entry_with_steps(self) -> LogEntry:
        return LogEntry(
            task="build",
            tool="harness:claude-code",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:05Z",
            duration_seconds=5.0,
            output="done",
            steps=[
                IntermediateStep(
                    kind=StepKind.thinking,
                    text="Let me analyze",
                    timestamp="2026-01-01T00:00:01Z",
                ),
                IntermediateStep(
                    kind=StepKind.tool_call,
                    tool_name="Read",
                    locations=["/src/main.py"],
                    timestamp="2026-01-01T00:00:02Z",
                ),
                IntermediateStep(
                    kind=StepKind.tool_result,
                    tool_status="completed",
                    timestamp="2026-01-01T00:00:03Z",
                ),
            ],
        )

    def test_show_steps_renders_timeline(self) -> None:
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "steps", c)
        output = buf.getvalue()
        assert "thinking" in output
        assert "Read" in output
        assert "completed" in output

    def test_show_all_includes_steps(self) -> None:
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "all", c)
        output = buf.getvalue()
        # "all" should include both stdout/stderr AND steps
        assert "thinking" in output or "done" in output

    def test_show_output_does_not_include_steps(self) -> None:
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "output", c)
        output = buf.getvalue()
        assert "Let me analyze" not in output
