"""WsHitlExecutor tests."""
from __future__ import annotations

import asyncio

import pytest
import yaml

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.api.ws_hitl import WsHitlExecutor
from app.services.api.ws_manager import WebSocketBroker
from app.services.executor.base import FlowContext
from app.services.store.filesystem import FilesystemStore


class _Sink:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.fixture
def store(tmp_path) -> FilesystemStore:
    s = FilesystemStore(tmp_path / ".atelier")
    conduit_dir = s.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\ndescription: x\ntasks:\n"
        "  - greet:\n      description: g\n      task: echo hi\n"
        "      tool: tool:bash\n      depends_on: []\n"
    )
    return s


def _ctx(store: FilesystemStore) -> FlowContext:
    flow_id = store.create_flow("hello", {})
    return FlowContext(flow_id=flow_id, store=store, inputs={})


async def test_executor_emits_hitl_request_envelope(store):
    sink = _Sink()
    broker = WebSocketBroker(send=sink)
    ctx = _ctx(store)
    broker.register_flow(ctx.flow_id)
    executor = WsHitlExecutor(broker=broker, flow_id=ctx.flow_id)

    task = TaskDefinition.model_validate(
        {
            "name": "approve",
            "description": "human gate",
            "task": "Please answer",
            "tool": ToolType.hitl,
            "depends_on": [],
            "inputs": {"confirm": "type yes"},
        }
    )

    async def respond_later() -> None:
        await asyncio.sleep(0.01)
        await broker.deliver_hitl_answer(ctx.flow_id, {"confirm": "yes"})

    asyncio.create_task(respond_later())
    result = await executor.execute(task, "Please answer", ctx)

    assert result.exit_code == 0
    assert sink.sent[0]["type"] == "hitl_request"
    assert sink.sent[0]["flow_id"] == ctx.flow_id
    assert any(
        item["name"] == "confirm" for item in sink.sent[0].get("inputs", [])
    )


async def test_executor_persists_answers_to_input_yaml(store):
    sink = _Sink()
    broker = WebSocketBroker(send=sink)
    ctx = _ctx(store)
    broker.register_flow(ctx.flow_id)
    executor = WsHitlExecutor(broker=broker, flow_id=ctx.flow_id)

    task = TaskDefinition.model_validate(
        {
            "name": "approve",
            "description": "g",
            "task": "x",
            "tool": ToolType.hitl,
            "depends_on": [],
            "inputs": {"name": "your name"},
        }
    )

    async def respond() -> None:
        await asyncio.sleep(0.01)
        await broker.deliver_hitl_answer(ctx.flow_id, {"name": "Alice"})

    asyncio.create_task(respond())
    await executor.execute(task, "x", ctx)

    saved = store.read_input(ctx.flow_id)
    assert saved["name"] == "Alice"
    assert ctx.inputs["name"] == "Alice"


async def test_executor_output_is_yaml_dump_of_answers(store):
    sink = _Sink()
    broker = WebSocketBroker(send=sink)
    ctx = _ctx(store)
    broker.register_flow(ctx.flow_id)
    executor = WsHitlExecutor(broker=broker, flow_id=ctx.flow_id)

    task = TaskDefinition.model_validate(
        {
            "name": "approve",
            "description": "g",
            "task": "x",
            "tool": ToolType.hitl,
            "depends_on": [],
            "inputs": {"choice": "pick"},
        }
    )

    async def respond() -> None:
        await asyncio.sleep(0.01)
        await broker.deliver_hitl_answer(ctx.flow_id, {"choice": "blue"})

    asyncio.create_task(respond())
    result = await executor.execute(task, "x", ctx)

    assert yaml.safe_load(result.output) == {"choice": "blue"}
