"""Engine: verify result.steps flows into LogEntry and TaskEvent."""
from __future__ import annotations

from typing import Any

import pytest

from app.modules.engine import Engine
from app.schemas.conduit import Conduit
from app.schemas.log import ExecutionResult, IntermediateStep, StepKind, TaskEvent
from app.services.executor.base import ExecutorBase
from app.services.store.filesystem import FilesystemStore


class StepsExecutor(ExecutorBase):
    """Executor that returns an ExecutionResult with pre-populated steps."""

    def __init__(self, steps: list[IntermediateStep]) -> None:
        """Initialize the executor with a fixed list of steps to emit.

        :param steps: intermediate steps returned with every execution.
        """
        self._steps = steps

    async def execute(self, task, resolved_command, context):
        """Return a successful ExecutionResult carrying the configured steps.

        :param task: task definition being executed.
        :param resolved_command: command string after template resolution.
        :param context: flow context provided by the engine.
        """
        return ExecutionResult(
            exit_code=0,
            output="done",
            stdout="done",
            steps=list(self._steps),
        )


@pytest.fixture
def store(tmp_path):
    """Provide a FilesystemStore rooted under the pytest temp path.

    :param tmp_path: pytest temp directory fixture.
    """
    return FilesystemStore(tmp_path / ".atelier")


def _conduit(tasks: list[dict[str, Any]], **kw: Any) -> Conduit:
    """Build a Conduit model from a list of task dicts plus optional fields.

    :param tasks: task dicts each containing a ``name`` and task fields.
    :param kw: extra top-level conduit fields (inputs, max_concurrency, ...).
    """
    body = {
        "name": "test",
        "description": "d",
        "tasks": [
            {t["name"]: {k: v for k, v in t.items() if k != "name"}}
            for t in tasks
        ],
        **kw,
    }
    return Conduit.model_validate(body)


async def test_steps_passed_to_log_entry(store) -> None:
    """result.steps must appear in the persisted LogEntry.

    :param store: FilesystemStore fixture.
    """
    steps = [
        IntermediateStep(kind=StepKind.thinking, text="analyzing"),
        IntermediateStep(kind=StepKind.tool_call, tool_name="Read"),
    ]
    conduit = _conduit(
        [
            {
                "name": "a",
                "description": "d",
                "task": "x",
                "tool": "tool:bash",
                "depends_on": [],
            }
        ]
    )
    engine = Engine({"tool:bash": StepsExecutor(steps)}, store)
    flow_id = await engine.run(conduit, {})
    logs = store.read_logs(flow_id)
    assert len(logs) == 1
    assert len(logs[0].steps) == 2
    assert logs[0].steps[0].kind == StepKind.thinking
    assert logs[0].steps[1].tool_name == "Read"


async def test_steps_passed_to_task_event(store) -> None:
    """result.steps must appear in the TaskEvent callback.

    :param store: FilesystemStore fixture.
    """
    steps = [IntermediateStep(kind=StepKind.tool_result, tool_status="completed")]
    conduit = _conduit(
        [
            {
                "name": "a",
                "description": "d",
                "task": "x",
                "tool": "tool:bash",
                "depends_on": [],
            }
        ]
    )
    events: list[TaskEvent] = []
    engine = Engine({"tool:bash": StepsExecutor(steps)}, store)
    await engine.run(conduit, {}, on_task_event=events.append)
    # Find the completed event (not skipped/cancelled)
    completed = [e for e in events if e.success]
    assert len(completed) == 1
    assert len(completed[0].steps) == 1
    assert completed[0].steps[0].tool_status == "completed"


async def test_empty_steps_when_executor_returns_none(store) -> None:
    """Steps default to [] when the executor doesn't populate them.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {
                "name": "a",
                "description": "d",
                "task": "x",
                "tool": "tool:bash",
                "depends_on": [],
            }
        ]
    )
    engine = Engine({"tool:bash": StepsExecutor([])}, store)
    flow_id = await engine.run(conduit, {})
    logs = store.read_logs(flow_id)
    assert logs[0].steps == []
