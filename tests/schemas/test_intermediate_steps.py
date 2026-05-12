"""Tests for IntermediateStep schema and steps fields on log models."""
from __future__ import annotations

import json

from app.schemas.log import (
    ExecutionResult,
    IntermediateStep,
    LogEntry,
    StepKind,
    TaskEvent,
)


class TestStepKindEnum:
    def test_thinking_value(self) -> None:
        """Verify StepKind.thinking maps to the expected string value."""
        assert StepKind.thinking == "thinking"

    def test_tool_call_value(self) -> None:
        """Verify StepKind.tool_call maps to the expected string value."""
        assert StepKind.tool_call == "tool_call"

    def test_tool_result_value(self) -> None:
        """Verify StepKind.tool_result maps to the expected string value."""
        assert StepKind.tool_result == "tool_result"


class TestIntermediateStep:
    def test_thinking_step_minimal(self) -> None:
        """Verify a minimal thinking step constructs with the expected fields."""
        step = IntermediateStep(kind=StepKind.thinking, text="Let me think...")
        assert step.kind == "thinking"
        assert step.text == "Let me think..."
        assert step.timestamp  # auto-populated

    def test_tool_call_step(self) -> None:
        """Verify a tool_call step retains the provided tool metadata."""
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_call_id="tc-1",
            tool_name="Read",
            tool_kind="read",
            tool_status="pending",
            tool_input="path=/foo/bar.py",
            locations=["/foo/bar.py"],
        )
        assert step.tool_name == "Read"
        assert step.locations == ["/foo/bar.py"]

    def test_tool_result_step(self) -> None:
        """Verify a tool_result step retains the completed status."""
        step = IntermediateStep(
            kind=StepKind.tool_result,
            tool_call_id="tc-1",
            tool_status="completed",
            tool_output="file contents here",
        )
        assert step.tool_status == "completed"

    def test_defaults_are_empty(self) -> None:
        """Verify all optional step fields default to empty values."""
        step = IntermediateStep(kind=StepKind.thinking)
        assert step.text == ""
        assert step.tool_call_id == ""
        assert step.tool_name == ""
        assert step.tool_kind == ""
        assert step.tool_status == ""
        assert step.tool_input == ""
        assert step.tool_output == ""
        assert step.locations == []

    def test_model_dump_includes_all_fields(self) -> None:
        """Verify model_dump emits the core IntermediateStep fields."""
        step = IntermediateStep(kind=StepKind.thinking, text="hi")
        dumped = step.model_dump()
        assert "kind" in dumped
        assert "timestamp" in dumped
        assert "text" in dumped


class TestStepsFieldOnModels:
    def test_execution_result_steps_default_empty(self) -> None:
        """Verify ExecutionResult.steps defaults to an empty list."""
        r = ExecutionResult()
        assert r.steps == []
        dumped = r.model_dump()
        assert dumped["steps"] == []

    def test_execution_result_with_steps(self) -> None:
        """Verify ExecutionResult preserves provided steps."""
        step = IntermediateStep(kind=StepKind.thinking, text="hmm")
        r = ExecutionResult(steps=[step])
        assert len(r.steps) == 1
        assert r.steps[0].text == "hmm"

    def test_log_entry_steps_default_empty(self) -> None:
        """Verify LogEntry.steps defaults to an empty list."""
        entry = LogEntry(
            task="t",
            tool="tool:bash",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:01Z",
        )
        assert entry.steps == []

    def test_log_entry_with_steps(self) -> None:
        """Verify LogEntry preserves provided steps."""
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Bash")
        entry = LogEntry(
            task="t",
            tool="tool:bash",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:01Z",
            steps=[step],
        )
        assert len(entry.steps) == 1

    def test_task_event_steps_default_empty(self) -> None:
        """Verify TaskEvent.steps defaults to an empty list."""
        event = TaskEvent(task="t", tool="tool:bash")
        assert event.steps == []

    def test_task_event_with_steps(self) -> None:
        """Verify TaskEvent preserves provided steps."""
        step = IntermediateStep(kind=StepKind.tool_result, tool_status="failed")
        event = TaskEvent(task="t", tool="tool:bash", steps=[step])
        assert len(event.steps) == 1

    def test_backwards_compat_log_entry_without_steps_field(self) -> None:
        """Old logs.json entries that don't have 'steps' should parse fine."""
        old_json = json.dumps(
            {
                "task": "build",
                "tool": "tool:bash",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "exit_code": 0,
            }
        )
        entry = LogEntry.model_validate_json(old_json)
        assert entry.steps == []
