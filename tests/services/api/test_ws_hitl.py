"""WsHitlExecutor tests."""
from __future__ import annotations

from typing import Any

import pytest
import yaml

from flow_atelier.schemas.conduit import TaskDefinition, ToolType
from flow_atelier.services.api.ws_hitl import WsHitlExecutor
from flow_atelier.services.executor.base import FlowContext
from flow_atelier.services.store.filesystem import FilesystemStore


@pytest.fixture
def store(tmp_path):
    """Filesystem-backed store fixture pre-seeded with a hello conduit.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    conduit_dir = s.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\ndescription: d\ntasks:\n  - t: {description: d, task: echo, tool: tool:bash, depends_on: []}\n"
    )
    return s


class _FakeBroker:
    """Minimal broker stub returning a fixed answer map.

    :param answers: the ``hitl_answer`` payload the WebSocket client "sent".
    """

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.sent: list[dict[str, Any]] = []

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def await_hitl_answer(self, flow_id, timeout=None):
        return self.answers


def _task() -> TaskDefinition:
    """Build a HITL TaskDefinition that declares two inputs."""
    return TaskDefinition(
        name="ask",
        description="d",
        task="I need some details:",
        tool=ToolType.hitl,
        depends_on=[],
        inputs={"confirm": "type yes", "notes": "any notes"},
    )


async def test_ws_hitl_collects_complete_answers(store):
    """A complete answer set succeeds and is persisted.

    :param store: filesystem store fixture.
    """
    flow_id = store.create_flow("hello", {})
    ctx = FlowContext(flow_id=flow_id, store=store, inputs={})
    broker = _FakeBroker({"confirm": "yes", "notes": "all good"})

    result = await WsHitlExecutor(broker, flow_id).execute(
        _task(), "I need some details:", ctx
    )

    assert result.exit_code == 0
    assert yaml.safe_load(result.output) == {"confirm": "yes", "notes": "all good"}
    assert ctx.inputs["confirm"] == "yes"
    on_disk = yaml.safe_load((store._flow_dir(flow_id) / "input.yaml").read_text())
    assert on_disk["confirm"] == "yes"
    assert on_disk["notes"] == "all good"


async def test_ws_hitl_missing_input_fails_loud(store):
    """An answer set omitting a declared input fails instead of under-resolving.

    :param store: filesystem store fixture.
    """
    flow_id = store.create_flow("hello", {})
    ctx = FlowContext(flow_id=flow_id, store=store, inputs={})
    broker = _FakeBroker({"confirm": "yes"})  # 'notes' omitted

    result = await WsHitlExecutor(broker, flow_id).execute(
        _task(), "I need some details:", ctx
    )

    assert result.exit_code == 1
    assert "notes" in result.stderr
    assert result.output == ""
    # Nothing should have been half-persisted from the incomplete answer set.
    assert "confirm" not in ctx.inputs
