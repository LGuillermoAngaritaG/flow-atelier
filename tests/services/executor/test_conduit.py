"""ConduitExecutor tests — focused on sub-task output propagation."""
from __future__ import annotations

from typing import Any

from app.schemas.conduit import Conduit, TaskDefinition, ToolType
from app.schemas.log import ExecutionResult, LogEntry
from app.schemas.progress import FlowStatus, Progress
from app.services.executor.base import FlowContext
from app.services.executor.conduit import ConduitExecutor


class _FakeStore:
    """Minimal store stand-in: only the methods ConduitExecutor calls."""

    def __init__(
        self,
        child_logs: list[LogEntry],
        child_status: FlowStatus,
        child_outputs: dict[str, str] | None = None,
        child_conduit: Conduit | None = None,
    ) -> None:
        """Initialize the fake store with canned child outputs.

        :param child_logs: log entries to return from read_logs.
        :param child_status: flow status to return from read_progress.
        :param child_outputs: per-task output map to return from read_outputs.
        :param child_conduit: conduit definition to return from read_conduit.
        """
        self._child_logs = child_logs
        self._child_status = child_status
        self._child_outputs = child_outputs or {}
        self._child_conduit = child_conduit

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

    def read_outputs(self, flow_id: str) -> dict[str, str]:  # noqa: ARG002
        """Return the canned per-task output map.

        :param flow_id: ignored — present only for interface compatibility.
        """
        return dict(self._child_outputs)

    def read_conduit(self, name: str) -> Conduit:  # noqa: ARG002
        """Return the canned child conduit definition.

        :param name: ignored — present only for interface compatibility.
        """
        assert self._child_conduit is not None
        return self._child_conduit


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


def _child_conduit(tasks: list[tuple[str, list[str]]]) -> Conduit:
    """Build a child Conduit from (name, depends_on) pairs.

    :param tasks: list of (task name, depends_on list) tuples.
    """
    return Conduit.model_validate(
        {
            "name": "child",
            "description": "d",
            "tasks": [
                {name: {"description": "d", "task": "x", "tool": "tool:bash",
                        "depends_on": deps}}
                for name, deps in tasks
            ],
        }
    )


async def _run_with_outputs(
    child_outputs: dict[str, str],
    child_conduit: Conduit,
    child_logs: list[LogEntry] | None = None,
) -> ExecutionResult:
    """Drive the ConduitExecutor with a fake store carrying outputs.yaml data.

    :param child_outputs: per-task output map for the fake read_outputs.
    :param child_conduit: child conduit definition for the fake read_conduit.
    :param child_logs: optional log entries for the fallback path.
    """
    store = _FakeStore(
        child_logs or [], FlowStatus.completed,
        child_outputs=child_outputs, child_conduit=child_conduit,
    )

    async def run_nested(name: str, inputs: dict[str, Any], parent: str) -> str:
        return "child-flow-id"

    ctx = FlowContext(
        flow_id="parent-flow-id",
        store=store,  # type: ignore[arg-type]
        inputs={},
        run_nested_conduit=run_nested,
    )
    return await ConduitExecutor().execute(_task(), "child", ctx)


async def test_output_uses_sink_task_outputs():
    """The child's output must come from its sink task, not whichever
    sub-task happened to log last."""
    conduit = _child_conduit([("a", []), ("b", ["a"])])
    # Log order says "alpha" logged last; the sink (b) says "beta".
    logs = [_log("b", "beta"), _log("a", "alpha")]
    result = await _run_with_outputs(
        {"a": "alpha", "b": "beta"}, conduit, child_logs=logs
    )
    assert result.output == "beta"


async def test_multiple_sinks_joined_in_definition_order():
    """Multiple sink outputs are joined in conduit definition order."""
    conduit = _child_conduit([("a", []), ("b", ["a"]), ("c", ["a"])])
    result = await _run_with_outputs(
        {"a": "alpha", "c": "out-c", "b": "out-b"}, conduit
    )
    assert result.output == "out-b\n\nout-c"


async def test_falls_back_to_logs_when_outputs_missing():
    """Old flows without outputs.yaml keep the last-successful-log behavior."""
    logs = [_log("a", "alpha"), _log("b", "beta")]
    result = await _run(logs)
    assert result.output == "beta"


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
