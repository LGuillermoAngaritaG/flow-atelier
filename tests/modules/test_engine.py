"""Engine unit tests using fake executors (no subprocesses)."""
import asyncio
from typing import Any

import pytest
import yaml

from app.modules.engine import ConduitValidationError, Engine
from app.schemas.conduit import Conduit, TaskDefinition, ToolType
from app.schemas.log import ExecutionResult
from app.schemas.progress import FlowStatus, TaskStatus
from app.services.executor.base import ExecutorBase, FlowContext
from app.services.store.filesystem import FilesystemStore


class FakeExecutor(ExecutorBase):
    def __init__(
        self,
        outputs: dict[str, str] | None = None,
        fail: set[str] | None = None,
        sleep: float = 0.0,
    ):
        self.outputs = outputs or {}
        self.fail = fail or set()
        self.sleep = sleep
        self.calls: list[str] = []

    async def execute(self, task, resolved_command, context):
        self.calls.append(task.name)
        if self.sleep:
            await asyncio.sleep(self.sleep)
        if task.name in self.fail:
            return ExecutionResult(exit_code=1, stderr="boom", output="")
        out = self.outputs.get(task.name, f"out-{task.name}")
        return ExecutionResult(exit_code=0, output=out, stdout=out)


@pytest.fixture
def store(tmp_path):
    return FilesystemStore(tmp_path / ".atelier")


def _conduit(tasks: list[dict[str, Any]], **kw: Any) -> Conduit:
    body = {
        "name": "test",
        "description": "d",
        "tasks": [{t["name"]: {k: v for k, v in t.items() if k != "name"}} for t in tasks],
        **kw,
    }
    return Conduit.model_validate(body)


async def test_linear_happy_path(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    fake = FakeExecutor()
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    p = store.read_progress(flow_id)
    assert p.status == FlowStatus.completed
    assert p.tasks["a"].status == TaskStatus.completed
    assert p.tasks["b"].status == TaskStatus.completed
    assert fake.calls == ["a", "b"]


async def test_parallel_fan_out(store):
    conduit = _conduit(
        [
            {"name": "root", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["root"]},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["root"]},
            {"name": "c", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a", "b"]},
        ]
    )
    fake = FakeExecutor(sleep=0.1)
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    p = store.read_progress(flow_id)
    assert p.status == FlowStatus.completed
    for name in ("root", "a", "b", "c"):
        assert p.tasks[name].status == TaskStatus.completed


async def test_conditional_branch_match_and_not_match(store):
    conduit = _conduit(
        [
            {"name": "review", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "deploy", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": ["review.output.match(APPROVE)"]},
            {"name": "rollback", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": ["review.output.not_match(APPROVE)"]},
        ]
    )
    fake = FakeExecutor(outputs={"review": "VERDICT: APPROVE"})
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    p = store.read_progress(flow_id)
    assert p.tasks["deploy"].status == TaskStatus.completed
    assert p.tasks["rollback"].status == TaskStatus.skipped
    assert "condition not met" in (p.tasks["rollback"].reason or "")


async def test_repeat_runs_n_times(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 3},
        ]
    )
    fake = FakeExecutor()
    engine = Engine({"tool:bash": fake}, store)
    await engine.run(conduit, {})
    assert fake.calls == ["a", "a", "a"]


async def test_repeat_fails_aborts(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5},
        ]
    )
    # Fail on the 2nd iteration by subclassing
    class FailSecond(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.count = 0

        async def execute(self, task, resolved_command, context):
            self.count += 1
            self.calls.append(task.name)
            if self.count == 2:
                return ExecutionResult(exit_code=1, stderr="boom")
            return ExecutionResult(exit_code=0, output=f"i{self.count}")

    fake = FailSecond()
    engine = Engine({"tool:bash": fake}, store)
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {})
    assert fake.count == 2  # stopped mid-repeat


async def test_fail_fast_cancels_siblings(store):
    conduit = _conduit(
        [
            {"name": "fail", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "slow", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "after", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["fail"]},
        ]
    )
    class Mixed(FakeExecutor):
        async def execute(self, task, resolved_command, context):
            self.calls.append(task.name)
            if task.name == "fail":
                return ExecutionResult(exit_code=1, stderr="boom")
            await asyncio.sleep(5)  # long — should be cancelled
            return ExecutionResult(exit_code=0, output="late")

    fake = Mixed()
    engine = Engine({"tool:bash": fake}, store)
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {})
    p = store.read_progress(fake_flow := store.list_flows()[0])
    assert p.status == FlowStatus.failed
    assert p.tasks["fail"].status == TaskStatus.failed
    assert p.tasks["slow"].status in (TaskStatus.cancelled, TaskStatus.failed)
    # 'after' depended on 'fail', so it was never started
    assert p.tasks["after"].status in (TaskStatus.cancelled, TaskStatus.skipped, TaskStatus.pending)


async def test_skip_propagation_via_template(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": ["a.output.match(YES)"]},
            # c depends on b via plain dep -> b skipped -> c skipped
            {"name": "c", "description": "d", "task": "echo {{b.output}}", "tool": "tool:bash",
             "depends_on": ["b"]},
        ]
    )
    fake = FakeExecutor(outputs={"a": "NO"})
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    p = store.read_progress(flow_id)
    assert p.tasks["b"].status == TaskStatus.skipped
    assert p.tasks["c"].status == TaskStatus.skipped


async def test_template_inputs_resolved(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "echo {{inputs.msg}}",
             "tool": "tool:bash", "depends_on": []},
        ],
        inputs={"msg": "desc"},
    )
    captured = {}

    class Capturing(FakeExecutor):
        async def execute(self, task, resolved_command, context):
            captured["cmd"] = resolved_command
            return ExecutionResult(exit_code=0, output="ok")

    fake = Capturing()
    engine = Engine({"tool:bash": fake}, store)
    await engine.run(conduit, {"msg": "hello"})
    assert captured["cmd"] == "echo hello"


async def test_missing_input_raises(store):
    conduit = _conduit(
        [{"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []}],
        inputs={"x": "required"},
    )
    engine = Engine({"tool:bash": FakeExecutor()}, store)
    with pytest.raises(ValueError, match="missing required inputs"):
        await engine.run(conduit, {})


async def test_cycle_detection(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["b"]},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    engine = Engine({"tool:bash": FakeExecutor()}, store)
    with pytest.raises(ConduitValidationError, match="circular"):
        await engine.run(conduit, {})


async def test_unknown_dep_target(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["ghost"]},
        ]
    )
    engine = Engine({"tool:bash": FakeExecutor()}, store)
    with pytest.raises(ConduitValidationError, match="unknown"):
        await engine.run(conduit, {})


async def test_invalid_regex(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": ["a.output.match([unclosed)"]},
        ]
    )
    engine = Engine({"tool:bash": FakeExecutor()}, store)
    with pytest.raises(ConduitValidationError):
        await engine.run(conduit, {})


async def test_concurrency_cap(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "c", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "d", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
        ],
        max_concurrency=2,
    )
    max_seen = 0
    active = 0
    lock = asyncio.Lock()

    class Cap(FakeExecutor):
        async def execute(self, task, resolved_command, context):
            nonlocal active, max_seen
            async with lock:
                active += 1
                if active > max_seen:
                    max_seen = active
            await asyncio.sleep(0.15)
            async with lock:
                active -= 1
            return ExecutionResult(exit_code=0, output="ok")

    fake = Cap()
    engine = Engine({"tool:bash": fake}, store)
    await engine.run(conduit, {})
    assert max_seen <= 2


async def test_on_task_event_fires_for_each_completed_task(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
            {"name": "b", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": ["a"]},
        ]
    )
    fake = FakeExecutor(outputs={"a": "alpha", "b": "beta"})
    engine = Engine({"tool:bash": fake}, store)
    events = []
    await engine.run(conduit, {}, on_task_event=events.append)
    assert [e.task for e in events] == ["a", "b"]
    assert events[0].output == "alpha" and events[0].success is True
    assert events[1].output == "beta" and events[1].exit_code == 0
    assert all(e.tool == "tool:bash" for e in events)


async def test_on_task_event_fires_for_failed_task(store):
    conduit = _conduit(
        [
            {"name": "boom", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
        ]
    )
    fake = FakeExecutor(fail={"boom"})
    engine = Engine({"tool:bash": fake}, store)
    events = []
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {}, on_task_event=events.append)
    assert len(events) == 1
    assert events[0].task == "boom"
    assert events[0].success is False
    assert events[0].exit_code == 1
    assert events[0].stderr == "boom"


async def test_on_task_event_callback_error_does_not_break_flow(store, capsys):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash", "depends_on": []},
        ]
    )
    fake = FakeExecutor()
    engine = Engine({"tool:bash": fake}, store)

    def bad_callback(event):
        raise RuntimeError("renderer exploded")

    flow_id = await engine.run(conduit, {}, on_task_event=bad_callback)
    p = store.read_progress(flow_id)
    assert p.status == FlowStatus.completed
    assert p.tasks["a"].status == TaskStatus.completed
    captured = capsys.readouterr()
    assert "renderer exploded" in captured.err


async def test_on_task_event_fires_per_repeat_iteration(store):
    conduit = _conduit(
        [
            {"name": "a", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 3},
        ]
    )
    fake = FakeExecutor()
    engine = Engine({"tool:bash": fake}, store)
    events = []
    await engine.run(conduit, {}, on_task_event=events.append)
    assert len(events) == 3
    assert [e.iteration for e in events] == [1, 2, 3]
    assert all(e.of == 3 for e in events)
