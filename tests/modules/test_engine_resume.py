"""Tests for engine resume-from-failed-flow functionality."""
from __future__ import annotations

from typing import Any

import pytest

from app.modules.engine import Engine
from app.schemas.conduit import Conduit
from app.schemas.log import ExecutionResult
from app.schemas.progress import FlowStatus, TaskStatus
from app.services.executor.base import ExecutorBase
from app.services.store.filesystem import FilesystemStore


class FakeExecutor(ExecutorBase):
    def __init__(
        self,
        outputs: dict[str, str] | None = None,
        fail: set[str] | None = None,
    ):
        """Initialize the fake executor.

        :param outputs: optional task-name to stdout mapping.
        :param fail: optional set of task names that should fail.
        """
        self.outputs = outputs or {}
        self.fail = fail or set()
        self.calls: list[str] = []

    async def execute(self, task, resolved_command, context):
        """Record the call and return a scripted ExecutionResult.

        :param task: task definition being executed.
        :param resolved_command: command string after template resolution.
        :param context: flow context provided by the engine.
        """
        self.calls.append(task.name)
        if task.name in self.fail:
            return ExecutionResult(exit_code=1, stderr="boom", output="")
        out = self.outputs.get(task.name, f"out-{task.name}")
        return ExecutionResult(exit_code=0, output=out, stdout=out)


@pytest.fixture
def store(tmp_path):
    """Provide a FilesystemStore rooted under the pytest temp path.

    :param tmp_path: pytest temp directory fixture.
    """
    return FilesystemStore(tmp_path / ".atelier")


def _conduit(tasks: list[dict[str, Any]], **kw: Any) -> Conduit:
    """Build a Conduit model from a list of task dicts plus optional fields.

    :param tasks: task dicts each containing a ``name`` and task fields.
    :param kw: extra top-level conduit fields.
    """
    body = {
        "name": "test",
        "description": "d",
        "tasks": [{t["name"]: {k: v for k, v in t.items() if k != "name"}} for t in tasks],
        **kw,
    }
    return Conduit.model_validate(body)


async def _seed_failed_flow(
    store: FilesystemStore,
    conduit: Conduit,
    fail: set[str],
    outputs: dict[str, str] | None = None,
) -> str:
    """Run a conduit to failure and return its flow_id.

    :param store: FilesystemStore fixture.
    :param conduit: conduit to run.
    :param fail: task names that should fail.
    :param outputs: optional task-name to output mapping for non-failing tasks.
    :returns: the flow_id of the failed run.
    """
    fake = FakeExecutor(outputs=outputs, fail=fail)
    engine = Engine({"tool:bash": fake}, store)
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {})
    return store.list_flows()[0]


# ---------------------------------------------------------------- resume happy path


async def test_resume_skips_completed_tasks(store):
    """Verify resume_from skips already-completed tasks and only runs the failed one.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    # Seed: task a completes, task b fails
    flow_id = await _seed_failed_flow(store, conduit, fail={"b"})

    # Resume: only task b should run
    fake = FakeExecutor(outputs={"b": "recovered"})
    engine = Engine({"tool:bash": fake}, store)
    result_id = await engine.run(conduit, {}, resume_from=flow_id)
    assert result_id == flow_id
    assert fake.calls == ["b"]

    p = store.read_progress(flow_id)
    assert p.status == FlowStatus.completed
    assert p.tasks["a"].status == TaskStatus.completed
    assert p.tasks["b"].status == TaskStatus.completed


async def test_resume_reuses_prior_outputs(store):
    """Verify resumed tasks can access outputs from completed tasks in the prior run.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "echo {{a.output}}", "tool": "tool:bash",
             "depends_on": ["a"]},
        ]
    )
    # Seed: a outputs "alpha", b fails
    flow_id = await _seed_failed_flow(store, conduit, fail={"b"}, outputs={"a": "alpha"})

    captured = {}

    class Capturing(FakeExecutor):
        async def execute(self, task, resolved_command, context):
            """Capture the resolved command.

            :param task: task definition being executed.
            :param resolved_command: command string after template resolution.
            :param context: flow context provided by the engine.
            """
            captured["cmd"] = resolved_command
            return ExecutionResult(exit_code=0, output="recovered")

    engine = Engine({"tool:bash": Capturing()}, store)
    await engine.run(conduit, {}, resume_from=flow_id)
    assert captured["cmd"] == "echo alpha"


async def test_resume_preserves_flow_id(store):
    """Verify the resumed flow reuses the same flow_id.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
        ]
    )
    flow_id = await _seed_failed_flow(store, conduit, fail={"a"})

    fake = FakeExecutor()
    engine = Engine({"tool:bash": fake}, store)
    result_id = await engine.run(conduit, {}, resume_from=flow_id)
    assert result_id == flow_id


# ---------------------------------------------------------------- resume edge cases


async def test_resume_three_task_pipeline_skips_first(store):
    """Verify resume in a 3-task pipeline skips completed tasks and runs from the failed point.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
            {"name": "c", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["b"]},
        ]
    )
    # a completes, b fails, c never starts
    flow_id = await _seed_failed_flow(store, conduit, fail={"b"})

    fake = FakeExecutor(outputs={"b": "ok-b", "c": "ok-c"})
    engine = Engine({"tool:bash": fake}, store)
    await engine.run(conduit, {}, resume_from=flow_id)
    assert fake.calls == ["b", "c"]


async def test_resume_fires_on_task_event_only_for_rerun_tasks(store):
    """Verify on_task_event only fires for tasks actually re-executed, not skipped ones.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    flow_id = await _seed_failed_flow(store, conduit, fail={"b"})

    fake = FakeExecutor(outputs={"b": "ok"})
    engine = Engine({"tool:bash": fake}, store)
    events = []
    await engine.run(conduit, {}, resume_from=flow_id, on_task_event=events.append)
    assert [e.task for e in events] == ["b"]


async def test_resume_fires_on_task_starting_for_rerun_tasks(store):
    """Verify on_task_starting fires for re-executed tasks.

    :param store: FilesystemStore fixture.
    """
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    flow_id = await _seed_failed_flow(store, conduit, fail={"b"})

    fake = FakeExecutor(outputs={"b": "ok"})
    engine = Engine({"tool:bash": fake}, store)
    starting = []
    await engine.run(
        conduit, {}, resume_from=flow_id,
        on_task_starting=lambda name, tool: starting.append(name),
    )
    assert starting == ["b"]
