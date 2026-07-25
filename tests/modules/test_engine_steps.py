"""Engine: verify result.steps flows into LogEntry and TaskEvent."""
from __future__ import annotations

from typing import Any

import pytest

from flow_atelier.modules.engine import Engine
from flow_atelier.schemas.conduit import Conduit
from flow_atelier.schemas.log import (
    ExecutionResult,
    IntermediateStep,
    StepKind,
    TaskEvent,
    TurnUsage,
)
from flow_atelier.services.executor.base import ExecutorBase
from flow_atelier.services.store.filesystem import FilesystemStore


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


class UsageExecutor(ExecutorBase):
    """Executor that returns an ExecutionResult carrying a fixed TurnUsage."""

    def __init__(self, usage: TurnUsage | None) -> None:
        """Initialize the executor with the usage to emit.

        :param usage: usage record returned with every execution (or None).
        """
        self._usage = usage

    async def execute(self, task, resolved_command, context):
        """Return a successful ExecutionResult carrying the configured usage.

        :param task: task definition being executed.
        :param resolved_command: command string after template resolution.
        :param context: flow context provided by the engine.
        """
        return ExecutionResult(
            exit_code=0, output="done", stdout="done", usage=self._usage
        )


async def test_usage_passed_to_log_entry(store) -> None:
    """result.usage must appear in the persisted LogEntry.

    :param store: FilesystemStore fixture.
    """
    usage = TurnUsage(input_tokens=1000, output_tokens=200, total_tokens=1200, cost=0.05)
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
    engine = Engine({"tool:bash": UsageExecutor(usage)}, store)
    flow_id = await engine.run(conduit, {})
    logs = store.read_logs(flow_id)
    assert logs[0].usage is not None
    assert logs[0].usage.total_tokens == 1200
    assert logs[0].usage.cost == 0.05


async def test_usage_none_persists_as_none(store) -> None:
    """usage defaults to None when the executor doesn't report it.

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
    engine = Engine({"tool:bash": UsageExecutor(None)}, store)
    flow_id = await engine.run(conduit, {})
    logs = store.read_logs(flow_id)
    assert logs[0].usage is None


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


class CancelMidTaskExecutor(ExecutorBase):
    """Executor that emits live steps, then dies as a killed task would."""

    async def execute(self, task, resolved_command, context):
        """Emit two steps through ``ctx.on_step``, then raise CancelledError.

        :param task: task definition being executed.
        :param resolved_command: command string after template resolution.
        :param context: flow context carrying the ``on_step`` hook.
        """
        import asyncio

        await context.on_step(
            IntermediateStep(kind=StepKind.thinking, text="halfway through")
        )
        await context.on_step(
            IntermediateStep(kind=StepKind.tool_call, tool_name="Bash")
        )
        raise asyncio.CancelledError


async def test_live_steps_survive_a_killed_task(store) -> None:
    """A task killed mid-run leaves no LogEntry but keeps its step trace.

    This is the whole point of steps.jsonl: `atelier stop` (or a crash) at
    minute 18 of a 20-minute agent task used to discard everything the user
    had just watched scroll by.

    :param store: FilesystemStore fixture.
    """
    import asyncio

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
    captured: list[str] = []
    engine = Engine({"tool:bash": CancelMidTaskExecutor()}, store)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(conduit, {}, on_flow_started=captured.append)

    flow_id = captured[0]
    assert store.read_logs(flow_id) == [], "a killed task must not log an entry"

    records = store.read_steps(flow_id)
    assert [r.step.kind for r in records] == [
        StepKind.thinking,
        StepKind.tool_call,
    ]
    assert records[0].step.text == "halfway through"
    assert all(r.task == "a" and r.iteration == 1 for r in records)


async def test_steps_are_persisted_as_they_arrive(store) -> None:
    """Steps hit steps.jsonl before the task returns, not after.

    :param store: FilesystemStore fixture.
    """
    seen: list[list] = []

    class ObservingExecutor(ExecutorBase):
        """Reads back steps.jsonl mid-task to prove the write already landed."""

        async def execute(self, task, resolved_command, context):
            """Persist a step, then read the store back before returning.

            :param task: task definition being executed.
            :param resolved_command: command string after template resolution.
            :param context: flow context carrying the ``on_step`` hook.
            """
            await context.on_step(
                IntermediateStep(kind=StepKind.thinking, text="mid-flight")
            )
            seen.append(store.read_steps(context.flow_id))
            return ExecutionResult(exit_code=0, output="done", stdout="done")

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
    engine = Engine({"tool:bash": ObservingExecutor()}, store)
    flow_id = await engine.run(conduit, {})

    # Visible mid-task, before any LogEntry existed.
    assert len(seen[0]) == 1
    assert seen[0][0].task == "a"
    assert seen[0][0].step.text == "mid-flight"
    # And still readable afterwards.
    assert len(store.read_steps(flow_id)) == 1
