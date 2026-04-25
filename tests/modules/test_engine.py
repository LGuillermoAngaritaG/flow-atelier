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


async def test_on_task_event_fires_for_skipped_task(store):
    """A task skipped via a conditional dependency must still emit a
    TaskEvent so renderers can show it (previously it disappeared)."""
    conduit = _conduit(
        [
            {"name": "review", "description": "d", "task": "x",
             "tool": "tool:bash", "depends_on": []},
            {"name": "deploy", "description": "d", "task": "x",
             "tool": "tool:bash",
             "depends_on": ["review.output.match(APPROVE)"]},
        ]
    )
    fake = FakeExecutor(outputs={"review": "REJECT"})
    engine = Engine({"tool:bash": fake}, store)
    events = []
    await engine.run(conduit, {}, on_task_event=events.append)
    by_task = {e.task: e for e in events}
    assert "deploy" in by_task
    assert by_task["deploy"].status == TaskStatus.skipped
    assert by_task["deploy"].reason  # populated with skip reason


async def test_on_task_event_fires_for_cancelled_task(store):
    """When fail-fast cancels still-pending tasks, those tasks must
    emit a TaskEvent so the user sees they were cancelled rather than
    just silently missing from the live output.
    """
    conduit = _conduit(
        [
            {"name": "fail", "description": "d", "task": "x",
             "tool": "tool:bash", "depends_on": []},
            {"name": "after", "description": "d", "task": "x",
             "tool": "tool:bash", "depends_on": ["fail"]},
        ]
    )
    fake = FakeExecutor(fail={"fail"})
    engine = Engine({"tool:bash": fake}, store)
    events = []
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {}, on_task_event=events.append)
    by_task = {e.task: e for e in events}
    assert "after" in by_task
    assert by_task["after"].status == TaskStatus.cancelled


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


# ---------------------------------------------------------------- until early-exit


class ScriptedExecutor(FakeExecutor):
    """Returns outputs from a scripted list, one per call."""

    def __init__(self, outputs_per_call: list[str], fail_on: int | None = None):
        super().__init__()
        self._scripted = outputs_per_call
        self._fail_on = fail_on  # 1-indexed iteration to fail on
        self._n = 0

    async def execute(self, task, resolved_command, context):
        self._n += 1
        self.calls.append(task.name)
        if self._fail_on is not None and self._n == self._fail_on:
            return ExecutionResult(
                exit_code=1, stderr="boom",
                output=self._scripted[self._n - 1],
            )
        out = self._scripted[self._n - 1]
        return ExecutionResult(exit_code=0, output=out, stdout=out)


async def test_until_match_breaks_loop_early(store):
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "until": "output.match(DONE)"},
        ]
    )
    fake = ScriptedExecutor(["wait", "DONE", "x", "x", "x"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 2
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.completed
    assert p.tasks["poll"].iteration == 2
    assert p.tasks["poll"].of == 5


async def test_until_match_never_fires_runs_full_repeat(store):
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "until": "output.match(NEVER)"},
        ]
    )
    fake = ScriptedExecutor(["a", "b", "c", "d", "e"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 5
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.completed
    assert p.tasks["poll"].iteration == 5
    assert p.tasks["poll"].of == 5


async def test_until_not_match_breaks_when_pattern_absent(store):
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "until": "output.not_match(RETRY)"},
        ]
    )
    fake = ScriptedExecutor(["RETRY", "RETRY", "done", "x", "x"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.completed
    assert p.tasks["poll"].iteration == 3
    assert p.tasks["poll"].of == 5


async def test_until_not_evaluated_on_failed_iteration(store):
    """Fail-fast wins over until — a failed iteration never triggers early-exit."""
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "until": "output.match(DONE)"},
        ]
    )
    # Iteration 2 fails; its output contains "DONE" — but fail-fast should win.
    fake = ScriptedExecutor(["wait", "DONE", "x", "x", "x"], fail_on=2)
    engine = Engine({"tool:bash": fake}, store)
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {})
    flow_id = store.list_flows()[0]
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.failed


async def test_while_match_breaks_when_pattern_absent(store):
    """`while: output.match(retry)` keeps iterating while output contains
    "retry" and breaks on the first iteration that doesn't."""
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "while": "output.match(retry)"},
        ]
    )
    fake = ScriptedExecutor(["retry", "retry", "done", "x", "x"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.completed
    assert p.tasks["poll"].iteration == 3
    assert p.tasks["poll"].of == 5


async def test_while_not_match_breaks_when_pattern_present(store):
    """`while: output.not_match(ready)` keeps iterating while output is
    NOT ready and breaks on the first iteration that emits "ready"."""
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "while": "output.not_match(ready)"},
        ]
    )
    fake = ScriptedExecutor(["pending", "pending", "ready now", "x", "x"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.completed
    assert p.tasks["poll"].iteration == 3
    assert p.tasks["poll"].of == 5


async def test_while_runs_full_repeat_when_predicate_holds(store):
    """If output keeps matching `while` regex, the loop never exits early."""
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 4,
             "while": "output.match(retry)"},
        ]
    )
    fake = ScriptedExecutor(["retry", "retry", "retry", "retry"])
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 4
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].iteration == 4
    assert p.tasks["poll"].of == 4


async def test_while_not_evaluated_on_failed_iteration(store):
    """Fail-fast wins over while too — failure stops the loop."""
    conduit = _conduit(
        [
            {"name": "poll", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "while": "output.match(retry)"},
        ]
    )
    fake = ScriptedExecutor(["retry", "retry", "x", "x", "x"], fail_on=2)
    engine = Engine({"tool:bash": fake}, store)
    with pytest.raises(RuntimeError):
        await engine.run(conduit, {})
    flow_id = store.list_flows()[0]
    p = store.read_progress(flow_id)
    assert p.tasks["poll"].status == TaskStatus.failed


# ---------------------------------------------------------------- conduit-scope predicate


class ScriptedConduitExecutor(FakeExecutor):
    """Fakes a tool:conduit executor with fabricated sub-task outputs.

    Lets us prove the engine evaluates loop predicates against sub-task
    outputs (not just the aggregate ``result.output``) without the
    ceremony of standing up a real nested conduit.
    """

    def __init__(
        self,
        sub_outputs_per_iteration: list[list[str]],
        aggregate_output: str = "nested conduit completed",
    ):
        super().__init__()
        self._scripted = sub_outputs_per_iteration
        self._aggregate = aggregate_output
        self._n = 0

    async def execute(self, task, resolved_command, context):
        self._n += 1
        self.calls.append(task.name)
        sub = self._scripted[self._n - 1]
        return ExecutionResult(
            exit_code=0,
            output=self._aggregate,
            stdout=self._aggregate,
            sub_outputs=list(sub),
        )


async def test_conduit_until_breaks_on_any_sub_task_match(store):
    """Until predicate over a tool:conduit task matches against any
    nested sub-task output, even when the aggregate ``output`` does not.

    Vacuousness guard (per SPEC §5): this test was confirmed to FAIL
    against the engine *without* the conduit-scope wiring — it runs all
    5 iterations because ``"PASS"`` never appears in
    ``aggregate_output``. It only passes once the engine reads
    ``result.sub_outputs`` for ``tool:conduit`` tasks.
    """
    conduit = _conduit(
        [
            {"name": "outer", "description": "d", "task": "child",
             "tool": "tool:conduit",
             "depends_on": [], "repeat": 5,
             "until": "output.match(PASS)"},
        ]
    )
    fake = ScriptedConduitExecutor(
        sub_outputs_per_iteration=[
            ["build ok", "tests FAIL"],
            ["build ok", "tests FAIL"],
            ["build ok", "tests PASS finally"],
            ["unused"],
            ["unused"],
        ],
        aggregate_output="nested conduit completed",
    )
    engine = Engine({"tool:conduit": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["outer"].status == TaskStatus.completed
    assert p.tasks["outer"].iteration == 3
    assert p.tasks["outer"].of == 5


async def test_conduit_while_continues_until_every_sub_task_matches(store):
    """`while: output.not_match(ready)` over a tool:conduit task keeps
    iterating while at least one sub-task is not ready, and breaks the
    iteration in which every sub-task output contains "ready" (the
    plan's M2 semantics for while + negated predicate)."""
    conduit = _conduit(
        [
            {"name": "outer", "description": "d", "task": "child",
             "tool": "tool:conduit",
             "depends_on": [], "repeat": 5,
             "while": "output.not_match(ready)"},
        ]
    )
    fake = ScriptedConduitExecutor(
        sub_outputs_per_iteration=[
            ["build pending", "service pending"],
            ["build ready", "service pending"],
            ["build ready", "service ready"],
            ["unused"],
            ["unused"],
        ],
    )
    engine = Engine({"tool:conduit": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["outer"].status == TaskStatus.completed
    assert p.tasks["outer"].iteration == 3
    assert p.tasks["outer"].of == 5


async def test_conduit_predicate_runs_full_repeat_when_no_sub_match(store):
    """If no sub-output ever matches the until regex, the loop runs to
    completion — no vacuous early exit."""
    conduit = _conduit(
        [
            {"name": "outer", "description": "d", "task": "child",
             "tool": "tool:conduit",
             "depends_on": [], "repeat": 3,
             "until": "output.match(PASS)"},
        ]
    )
    fake = ScriptedConduitExecutor(
        sub_outputs_per_iteration=[
            ["build ok", "tests fail"],
            ["build ok", "tests fail"],
            ["build ok", "tests fail"],
        ],
        aggregate_output="nested conduit completed",
    )
    engine = Engine({"tool:conduit": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert len(fake.calls) == 3
    p = store.read_progress(flow_id)
    assert p.tasks["outer"].iteration == 3


async def test_until_early_exit_publishes_output_to_downstream(store):
    """Output from the early-exit iteration must reach downstream conditional deps."""
    conduit = _conduit(
        [
            {"name": "up", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": [], "repeat": 5,
             "until": "output.match(DONE)"},
            {"name": "down", "description": "d", "task": "x", "tool": "tool:bash",
             "depends_on": ["up.output.match(DONE)"]},
        ]
    )

    class ByName(FakeExecutor):
        def __init__(self):
            super().__init__()
            self._up_n = 0

        async def execute(self, task, resolved_command, context):
            self.calls.append(task.name)
            if task.name == "up":
                self._up_n += 1
                out = "DONE" if self._up_n == 2 else "wait"
                return ExecutionResult(exit_code=0, output=out, stdout=out)
            return ExecutionResult(exit_code=0, output="down-ran", stdout="down-ran")

    fake = ByName()
    engine = Engine({"tool:bash": fake}, store)
    flow_id = await engine.run(conduit, {})
    assert fake.calls.count("up") == 2
    assert "down" in fake.calls
    p = store.read_progress(flow_id)
    assert p.tasks["down"].status == TaskStatus.completed
