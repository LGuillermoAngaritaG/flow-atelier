"""ConduitExecutor tests — focused on sub-task output propagation."""
from __future__ import annotations

from typing import Any

from app.schemas.conduit import TaskDefinition, ToolType
from app.schemas.log import ExecutionResult, LogEntry
from app.schemas.progress import FlowStatus, Progress
from app.services.executor.base import FlowContext
from app.services.executor.conduit import ConduitExecutor


class _FakeStore:
    """Minimal store stand-in: only the methods ConduitExecutor calls."""

    def __init__(
        self, child_logs: list[LogEntry], child_status: FlowStatus
    ) -> None:
        """Initialize the fake store with canned child outputs.

        :param child_logs: log entries to return from read_logs.
        :param child_status: flow status to return from read_progress.
        """
        self._child_logs = child_logs
        self._child_status = child_status

    def read_logs(self, flow_id: str) -> list[LogEntry]:  # noqa: ARG002
        """Return the canned child log entries.

        :param flow_id: ignored — present only for interface compatibility.
        """
        return list(self._child_logs)

    def read_progress(self, flow_id: str) -> Progress:  # noqa: ARG002
        """Return a Progress snapshot with the canned status.

        :param flow_id: ignored — present only for interface compatibility.
        """
        return Progress(status=self._child_status, tasks={}, started_at="x")


def _task(child_name: str = "child") -> TaskDefinition:
    """Build a conduit TaskDefinition pointing at a nested conduit.

    :param child_name: name of the nested conduit to invoke.
    """
    return TaskDefinition(
        name="outer",
        description="d",
        task=child_name,
        tool=ToolType.conduit,
        depends_on=[],
    )


def _log(task: str, output: str, exit_code: int = 0) -> LogEntry:
    """Build a LogEntry stub for a child sub-task.

    :param task: name of the sub-task.
    :param output: captured stdout for the sub-task.
    :param exit_code: process exit code.
    """
    return LogEntry(
        task=task, tool="tool:bash", iteration=1, of=1, command="x",
        output=output, exit_code=exit_code,
        started_at="2026-04-24T00:00:00Z", finished_at="2026-04-24T00:00:01Z",
    )


async def _run(
    child_logs: list[LogEntry], status: FlowStatus = FlowStatus.completed
) -> ExecutionResult:
    """Drive the ConduitExecutor against a fake nested conduit run.

    :param child_logs: log entries the fake store will report for the child.
    :param status: child FlowStatus to report from read_progress.
    """
    store = _FakeStore(child_logs, status)

    async def run_nested(name: str, inputs: dict[str, Any], parent: str) -> str:
        """Fake nested conduit launcher returning a stub flow id.

        :param name: nested conduit name.
        :param inputs: inputs passed to the nested conduit.
        :param parent: parent flow id.
        """
        return "child-flow-id"

    ctx = FlowContext(
        flow_id="parent-flow-id",
        store=store,  # type: ignore[arg-type]
        inputs={},
        run_nested_conduit=run_nested,
    )
    return await ConduitExecutor().execute(_task(), "child", ctx)


async def test_sub_outputs_collects_every_log_entry_in_order():
    """Verify sub_outputs preserves the order of child log entries."""
    logs = [
        _log("step_a", "alpha"),
        _log("step_b", "beta"),
        _log("step_c", "gamma"),
    ]
    result = await _run(logs)
    assert result.sub_outputs == ["alpha", "beta", "gamma"]


async def test_sub_outputs_empty_when_child_has_no_logs():
    """Verify sub_outputs is empty when the child produced no log entries."""
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


async def test_inputs_resolve_loop_previous_from_context_history():
    """Verify nested-conduit inputs resolve {{loop.previous}} against the
    loop history threaded in via FlowContext."""
    captured: dict[str, Any] = {}

    async def run_nested(name: str, inputs: dict[str, Any], parent: str) -> str:
        """Capture the resolved child inputs, return a stub flow id.

        :param name: nested conduit name.
        :param inputs: resolved inputs passed to the nested conduit.
        :param parent: parent flow id.
        """
        captured.update(inputs)
        return "child-flow-id"

    task = TaskDefinition(
        name="outer",
        description="d",
        task="child",
        tool=ToolType.conduit,
        depends_on=[],
        inputs={"task": "got=[{{loop.previous}}]"},
    )
    ctx = FlowContext(
        flow_id="parent-flow-id",
        store=_FakeStore([], FlowStatus.completed),  # type: ignore[arg-type]
        inputs={},
        run_nested_conduit=run_nested,
        loop_history=["earlier"],
    )
    await ConduitExecutor().execute(task, "child", ctx)
    assert captured["task"] == "got=[earlier]"


def test_execution_result_default_sub_outputs_is_empty_list():
    """Verify ExecutionResult.sub_outputs defaults to a fresh empty list."""
    r = ExecutionResult()
    assert r.sub_outputs == []
    # mutating one instance must not affect a freshly-built one
    r.sub_outputs.append("x")
    assert ExecutionResult().sub_outputs == []
