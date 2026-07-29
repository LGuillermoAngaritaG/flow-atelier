"""Test WsPromptSink sends step envelopes via the broker."""
from __future__ import annotations

import asyncio

from flow_atelier.modules.engine import _current_task_ctx
from flow_atelier.schemas.log import IntermediateStep, StepKind
from flow_atelier.services.api.ws_manager import WebSocketBroker
from flow_atelier.services.api.ws_sink import WsPromptSink


async def test_display_step_sends_step_envelope() -> None:
    """display_step should forward an IntermediateStep as a step envelope."""
    sent: list[dict] = []

    class FakeBroker:
        async def send(self, payload: dict) -> None:
            sent.append(payload)

    broker = FakeBroker()
    sink = WsPromptSink(broker=broker, flow_id="flow-123")  # type: ignore[arg-type]

    token = _current_task_ctx.set("my-task")
    try:
        step = IntermediateStep(kind=StepKind.thinking, text="analyzing input")
        await sink.display_step(step)

        assert len(sent) == 1
    finally:
        _current_task_ctx.reset(token)
    msg = sent[0]
    assert msg["type"] == "step"
    assert msg["flow_id"] == "flow-123"
    assert msg["task"] == "my-task"
    assert msg["step"]["kind"] == "thinking"
    assert msg["step"]["text"] == "analyzing input"


async def test_display_step_reads_current_task_from_contextvar() -> None:
    """display_step should read the task name from _current_task_ctx."""
    sent: list[dict] = []

    class FakeBroker:
        async def send(self, payload: dict) -> None:
            sent.append(payload)

    broker = FakeBroker()
    sink = WsPromptSink(broker=broker, flow_id="flow-456")  # type: ignore[arg-type]

    token = _current_task_ctx.set("other-task")
    try:
        step = IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
        await sink.display_step(step)

        assert sent[0]["task"] == "other-task"
    finally:
        _current_task_ctx.reset(token)


# ── interactive agent I/O ─────────────────────────────────────────────────


async def test_display_streams_an_agent_message_envelope() -> None:
    """display should forward agent prose chunks as agent_message."""
    sent: list[dict] = []
    broker = WebSocketBroker(send=_recorder(sent))
    sink = WsPromptSink(broker=broker, flow_id="flow-123")

    token = _current_task_ctx.set("ask")
    try:
        await sink.display("What colour ")
        await sink.display("should it be?")
    finally:
        _current_task_ctx.reset(token)

    assert [m["text"] for m in sent] == ["What colour ", "should it be?"]
    assert all(m["type"] == "agent_message" for m in sent)
    assert all(m["flow_id"] == "flow-123" and m["task"] == "ask" for m in sent)


async def test_request_input_emits_request_and_awaits_the_answer() -> None:
    """request_input should emit agent_input_request and return the answer."""
    sent: list[dict] = []
    broker = WebSocketBroker(send=_recorder(sent))
    sink = WsPromptSink(broker=broker, flow_id="flow-123")

    token = _current_task_ctx.set("ask")
    try:
        pending = asyncio.create_task(sink.request_input("your reply:"))
        # Let the sink emit its request before answering it.
        for _ in range(10):
            await asyncio.sleep(0)
            if sent:
                break
        assert sent, "no agent_input_request was emitted"
        request = sent[-1]
        assert request["type"] == "agent_input_request"
        assert request["flow_id"] == "flow-123"
        assert request["task"] == "ask"
        assert request["prompt"] == "your reply:"
        assert request["request_id"]
        assert not pending.done()

        await broker.deliver_agent_input_answer(
            "flow-123", request["request_id"], "blue"
        )
        assert await pending == "blue"
    finally:
        _current_task_ctx.reset(token)

    # Answered requests are cleaned up: the same id cannot be reused.
    try:
        await broker.deliver_agent_input_answer(
            "flow-123", request["request_id"], "again"
        )
    except KeyError:
        pass
    else:  # pragma: no cover - only reached on a regression
        raise AssertionError("stale request id was still answerable")


async def test_request_input_cleans_up_when_cancelled() -> None:
    """A cancelled turn must not leave the request answerable."""
    sent: list[dict] = []
    broker = WebSocketBroker(send=_recorder(sent))
    sink = WsPromptSink(broker=broker, flow_id="flow-123")

    pending = asyncio.create_task(sink.request_input("your reply:"))
    for _ in range(10):
        await asyncio.sleep(0)
        if sent:
            break
    request_id = sent[-1]["request_id"]
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass

    try:
        await broker.deliver_agent_input_answer("flow-123", request_id, "late")
    except KeyError:
        return
    raise AssertionError("cancelled request was still answerable")


def _recorder(sink: list[dict]):
    """Build an async send callable that appends payloads to ``sink``.

    :param sink: list collecting the outbound envelopes.
    """
    async def _send(payload: dict) -> None:
        """Record one outbound envelope.

        :param payload: envelope dict to capture.
        """
        sink.append(payload)

    return _send
