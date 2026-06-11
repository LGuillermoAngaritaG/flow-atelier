"""Test WsPromptSink sends step envelopes via the broker."""
from __future__ import annotations

import pytest

from flow_atelier.modules.engine import _current_task_ctx
from flow_atelier.schemas.log import IntermediateStep, StepKind
from flow_atelier.services.api.ws_sink import WsPromptSink
from flow_atelier.services.executor.prompt_sink import PermissionOption


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


async def test_request_permission_denies_all_requests() -> None:
    """request_permission should deny all requests with a PermissionError."""
    sink = WsPromptSink(broker=None, flow_id="f1")  # type: ignore[arg-type]
    options = [
        PermissionOption(id="allow", label="Allow"),
        PermissionOption(id="deny", label="Deny"),
    ]
    with pytest.raises(PermissionError, match="does not support interactive permission"):
        await sink.request_permission("summary", options)
