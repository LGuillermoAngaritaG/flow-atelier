"""ConduitExecutor tests — focused on sub-task output propagation."""
from __future__ import annotations

from typing import Any

import pytest

from app.schemas.conduit import TaskDefinition, ToolType
from app.schemas.log import ExecutionResult, LogEntry
from app.schemas.progress import FlowStatus, Progress, TaskStatus
from app.services.executor.base import FlowContext
from app.services.executor.conduit import ConduitExecutor


class _FakeStore:
    """Minimal store stand-in: only the methods ConduitExecutor calls."""

    def __init__(
        self, child_logs: list[LogEntry], child_status: FlowStatus
    ) -> None:
        self._child_logs = child_logs
        self._child_status = child_status

    def read_logs(self, flow_id: str) -> list[LogEntry]:  # noqa: ARG002
        return list(self._child_logs)

    def read_progress(self, flow_id: str) -> Progress:  # noqa: ARG002
        return Progress(status=self._child_status, tasks={}, started_at="x")


def _task(child_name: str = "child") -> TaskDefinition:
    return TaskDefinition(
        name="outer",
        description="d",
        task=child_name,
        tool=ToolType.conduit,
        depends_on=[],
    )


def _log(task: str, output: str, exit_code: int = 0) -> LogEntry:
    return LogEntry(
        task=task, tool="tool:bash", iteration=1, of=1, command="x",
        output=output, exit_code=exit_code,
        started_at="2026-04-24T00:00:00Z", finished_at="2026-04-24T00:00:01Z",
    )


async def _run(
    child_logs: list[LogEntry], status: FlowStatus = FlowStatus.completed
) -> ExecutionResult:
    store = _FakeStore(child_logs, status)

    async def run_nested(name: str, inputs: dict[str, Any], parent: str) -> str:
        return "child-flow-id"

    ctx = FlowContext(
        flow_id="parent-flow-id",
        store=store,  # type: ignore[arg-type]
        inputs={},
        run_nested_conduit=run_nested,
    )
    return await ConduitExecutor().execute(_task(), "child", ctx)


async def test_sub_outputs_collects_every_log_entry_in_order():
    logs = [
        _log("step_a", "alpha"),
        _log("step_b", "beta"),
        _log("step_c", "gamma"),
    ]
    result = await _run(logs)
    assert result.sub_outputs == ["alpha", "beta", "gamma"]


async def test_sub_outputs_empty_when_child_has_no_logs():
    result = await _run([])
    assert result.sub_outputs == []


async def test_sub_outputs_includes_failed_iterations():
    """Predicate evaluation should see all sub-task outputs, including
    failed ones — the engine still decides what to do with them."""
    logs = [
        _log("step_a", "ok"),
        _log("step_b", "boom", exit_code=1),
    ]
    result = await _run(logs, status=FlowStatus.failed)
    assert result.sub_outputs == ["ok", "boom"]


def test_execution_result_default_sub_outputs_is_empty_list():
    r = ExecutionResult()
    assert r.sub_outputs == []
    # mutating one instance must not affect a freshly-built one
    r.sub_outputs.append("x")
    assert ExecutionResult().sub_outputs == []
