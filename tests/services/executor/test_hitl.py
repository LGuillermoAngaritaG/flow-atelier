"""HitlExecutor tests."""
import builtins

import pytest
import yaml

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import FlowContext
from app.services.executor.hitl import HitlExecutor
from app.services.store.filesystem import FilesystemStore


@pytest.fixture
def store(tmp_path):
    s = FilesystemStore(tmp_path / ".atelier")
    conduit_dir = s.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\ndescription: d\ntasks:\n  - t: {description: d, task: echo, tool: tool:bash, depends_on: []}\n"
    )
    return s


def _task() -> TaskDefinition:
    return TaskDefinition(
        name="ask",
        description="d",
        task="I need some details:",
        tool=ToolType.hitl,
        depends_on=[],
        inputs={"confirm": "type yes", "notes": "any notes"},
    )


async def test_hitl_collects_and_persists(store, monkeypatch, capsys):
    flow_id = store.create_flow("hello", {"env": "staging"})
    ctx = FlowContext(flow_id=flow_id, store=store, inputs={"env": "staging"})

    answers = iter(["yes", "all good"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    result = await HitlExecutor().execute(_task(), "I need some details:", ctx)

    parsed_output = yaml.safe_load(result.output)
    assert parsed_output == {"confirm": "yes", "notes": "all good"}

    assert ctx.inputs["confirm"] == "yes"
    assert ctx.inputs["notes"] == "all good"

    on_disk = yaml.safe_load(
        (store._flow_dir(flow_id) / "input.yaml").read_text()
    )
    assert on_disk["confirm"] == "yes"
    assert on_disk["notes"] == "all good"
    assert on_disk["env"] == "staging"

    captured = capsys.readouterr()
    assert "I need some details" in captured.out
    assert "needs the following inputs" in captured.out


async def test_hitl_overwrite_collision(store, monkeypatch):
    flow_id = store.create_flow("hello", {"confirm": "previous"})
    ctx = FlowContext(flow_id=flow_id, store=store, inputs={"confirm": "previous"})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "new")
    await HitlExecutor().execute(
        TaskDefinition(
            name="ask",
            description="d",
            task="",
            tool=ToolType.hitl,
            depends_on=[],
            inputs={"confirm": "again?"},
        ),
        "",
        ctx,
    )
    data = yaml.safe_load((store._flow_dir(flow_id) / "input.yaml").read_text())
    assert data["confirm"] == "new"
    assert ctx.inputs["confirm"] == "new"
