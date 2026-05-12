"""Tests for step rendering in task event panels and log entries."""
from __future__ import annotations

import io

from rich.console import Console
from rich.text import Text

from app.cli.rendering.render import (
    _render_log_entry,
    _render_orchestration_msg,
    _render_step,
    _render_task_event,
)
from app.schemas.log import IntermediateStep, LogEntry, StepKind, TaskEvent


def _console() -> tuple[Console, io.StringIO]:
    """Build a Rich console writing to an in-memory buffer for assertions."""
    buf = io.StringIO()
    c = Console(file=buf, no_color=True, width=120)
    return c, buf


# ─── Tests for _render_step() shared function ─────────────────────────────


class TestRenderStep:
    def test_returns_rich_text(self) -> None:
        """Verify _render_step returns a Rich Text instance."""
        step = IntermediateStep(kind=StepKind.thinking, text="hello")
        result = _render_step(step)
        assert isinstance(result, Text)

    def test_thinking_glyph(self) -> None:
        """Verify the thinking glyph is rendered for thinking steps."""
        step = IntermediateStep(kind=StepKind.thinking, text="some thought")
        result = _render_step(step)
        plain = result.plain
        assert "💭" in plain

    def test_thinking_text_truncated_at_120(self) -> None:
        """Verify thinking text is truncated to 120 characters with ellipsis."""
        long_text = "a" * 200
        step = IntermediateStep(kind=StepKind.thinking, text=long_text)
        result = _render_step(step)
        plain = result.plain
        # Should contain only 120 chars of text plus "..."
        assert "a" * 120 in plain
        assert "..." in plain
        assert "a" * 121 not in plain

    def test_thinking_short_text_no_ellipsis(self) -> None:
        """Verify short thinking text is rendered without an ellipsis."""
        step = IntermediateStep(kind=StepKind.thinking, text="short")
        result = _render_step(step)
        plain = result.plain
        assert "..." not in plain
        assert "short" in plain

    def test_tool_call_glyph(self) -> None:
        """Verify the tool-call glyph is rendered for tool_call steps."""
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
        result = _render_step(step)
        plain = result.plain
        assert "🔧" in plain

    def test_tool_call_shows_name(self) -> None:
        """Verify the tool name is rendered in the tool_call line."""
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
        result = _render_step(step)
        plain = result.plain
        assert "Read" in plain

    def test_tool_call_with_location(self) -> None:
        """Verify locations are rendered when present on a tool_call."""
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Read",
            locations=["/src/main.py"],
        )
        result = _render_step(step)
        plain = result.plain
        assert "/src/main.py" in plain

    def test_tool_call_without_location(self) -> None:
        """Verify a tool_call without a location still renders the name."""
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Task")
        result = _render_step(step)
        plain = result.plain
        assert "Task" in plain

    def test_tool_result_success_glyph(self) -> None:
        """Verify completed tool_results render the success glyph."""
        step = IntermediateStep(kind=StepKind.tool_result, tool_status="completed")
        result = _render_step(step)
        plain = result.plain
        assert "✓" in plain
        assert "completed" in plain

    def test_tool_result_failure_glyph(self) -> None:
        """Verify failed tool_results render the failure glyph."""
        step = IntermediateStep(kind=StepKind.tool_result, tool_status="failed")
        result = _render_step(step)
        plain = result.plain
        assert "✗" in plain
        assert "failed" in plain

    def test_thinking_indented_2_spaces(self) -> None:
        """Verify thinking lines are indented by 2 spaces."""
        step = IntermediateStep(kind=StepKind.thinking, text="hi")
        result = _render_step(step)
        plain = result.plain
        assert plain.startswith("  ")

    def test_tool_call_indented_2_spaces(self) -> None:
        """Verify tool_call lines are indented by 2 spaces."""
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
        result = _render_step(step)
        plain = result.plain
        assert plain.startswith("  ")

    def test_tool_result_indented_5_spaces(self) -> None:
        """Verify tool_result lines are indented by 5 spaces."""
        step = IntermediateStep(kind=StepKind.tool_result, tool_status="completed")
        result = _render_step(step)
        plain = result.plain
        assert plain.startswith("     ")


class TestRenderTaskEventStepSummary:
    def test_step_summary_shown_for_success_with_steps(self) -> None:
        """Verify the step summary is rendered for successful tasks with steps."""
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
        """Verify no step summary is rendered when steps are empty."""
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
        """Build a LogEntry populated with a representative steps timeline."""
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
        """Verify the steps view renders glyphs and tool names from the timeline."""
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "steps", c)
        output = buf.getvalue()
        # New format uses emoji glyphs
        assert "💭" in output
        assert "Read" in output
        assert "✓" in output
        assert "completed" in output

    def test_show_steps_uses_short_timestamps(self) -> None:
        """Verify the steps view renders short timestamps, not full dates."""
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "steps", c)
        output = buf.getvalue()
        # Should NOT contain full date format, only HH:MM
        assert "2026-01-01" not in output

    def test_show_steps_tool_result_indented(self) -> None:
        """Tool results should be indented under their tool call (no timestamp)."""
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "steps", c)
        output = buf.getvalue()
        # Tool result line should NOT have a HH:MM timestamp prefix
        for line in output.splitlines():
            if "✓" in line and "completed" in line:
                # Should not contain a time like "19:00" before the glyph
                before_check = line.split("✓")[0]
                # No digit:digit pattern in the indent area
                import re
                assert not re.search(r"\d{2}:\d{2}", before_check)
                break

    def test_show_all_includes_steps(self) -> None:
        """Verify the `all` view renders both output and step content."""
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "all", c)
        output = buf.getvalue()
        # "all" should include both stdout/stderr AND steps
        assert "💭" in output or "done" in output

    def test_show_output_does_not_include_steps(self) -> None:
        """Verify the `output` view omits step content."""
        entry = self._entry_with_steps()
        c, buf = _console()
        _render_log_entry(entry, "output", c)
        output = buf.getvalue()
        assert "Let me analyze" not in output


# ─── Tests for _render_orchestration_msg() ─────────────────────────────────


class TestRenderOrchestrationMsg:
    def test_returns_rich_text(self) -> None:
        """Verify _render_orchestration_msg returns a Rich Text instance."""
        result = _render_orchestration_msg("loading conduit")
        assert isinstance(result, Text)

    def test_has_dot_prefix(self) -> None:
        """Verify orchestration messages are prefixed with the dot glyph."""
        result = _render_orchestration_msg("loading conduit")
        plain = result.plain
        assert plain.startswith("·")

    def test_contains_message(self) -> None:
        """Verify the orchestration message body is preserved verbatim."""
        result = _render_orchestration_msg('running task "lint" [tool:bash]')
        plain = result.plain
        assert 'running task "lint" [tool:bash]' in plain
