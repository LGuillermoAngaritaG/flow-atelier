"""WebSocket message envelope schema tests."""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.ws import (
    CancelMessage,
    ClientMessage,
    ErrorMessage,
    FlowCompleteMessage,
    FlowFailedMessage,
    HitlAnswerMessage,
    HitlRequestMessage,
    LogMessage,
    RunMessage,
    ServerMessage,
    StartedMessage,
    StepMessage,
    StepStatusMessage,
)


def _client(payload: dict) -> object:
    """Validate a payload as a ClientMessage.

    :param payload: raw dict payload to validate.
    """
    return TypeAdapter(ClientMessage).validate_python(payload)


def _server(payload: dict) -> object:
    """Validate a payload as a ServerMessage.

    :param payload: raw dict payload to validate.
    """
    return TypeAdapter(ServerMessage).validate_python(payload)


def test_client_run_validates():
    """Verify a client `run` message validates into RunMessage."""
    msg = _client(
        {
            "type": "run",
            "flow_id": "T-1",
            "conduit_name": "x",
            "inputs": {"a": 1},
            "run_path": "/abs",
        }
    )
    assert isinstance(msg, RunMessage)
    assert msg.flow_id == "T-1"
    assert msg.run_path == "/abs"


def test_client_hitl_answer_validates():
    """Verify a client `hitl_answer` message validates."""
    msg = _client(
        {"type": "hitl_answer", "flow_id": "T-1", "answers": {"q": "y"}}
    )
    assert isinstance(msg, HitlAnswerMessage)
    assert msg.answers == {"q": "y"}


def test_client_cancel_validates():
    """Verify a client `cancel` message validates."""
    msg = _client({"type": "cancel", "flow_id": "T-1"})
    assert isinstance(msg, CancelMessage)
    assert msg.flow_id == "T-1"


def test_client_unknown_type_rejected():
    """Verify an unknown client message type is rejected."""
    with pytest.raises(ValidationError):
        _client({"type": "explode", "flow_id": "T-1"})


def test_server_started_validates():
    """Verify a server `started` message validates."""
    msg = _server({"type": "started", "flow_id": "T-1"})
    assert isinstance(msg, StartedMessage)


def test_server_log_validates_with_real_logentry():
    """Verify a server `log` message validates with a real LogEntry."""
    log_entry = {
        "task": "echo",
        "tool": "tool:bash",
        "iteration": 1,
        "of": 1,
        "command": "echo hi",
        "stdout": "hi\n",
        "stderr": "",
        "exit_code": 0,
        "output": "hi\n",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "duration_seconds": 1.0,
    }
    msg = _server({"type": "log", "flow_id": "T-1", "entry": log_entry})
    assert isinstance(msg, LogMessage)
    assert msg.entry.task == "echo"


def test_server_step_status_validates():
    """Verify a server `step_status` message validates."""
    msg = _server(
        {
            "type": "step_status",
            "flow_id": "T-1",
            "step": "build",
            "status": "running",
        }
    )
    assert isinstance(msg, StepStatusMessage)
    assert msg.step == "build"
    assert msg.status == "running"


def test_server_hitl_request_validates():
    """Verify a server `hitl_request` message validates."""
    msg = _server({"type": "hitl_request", "flow_id": "T-1"})
    assert isinstance(msg, HitlRequestMessage)


def test_server_flow_complete_validates():
    """Verify a server `flow_complete` message validates."""
    msg = _server({"type": "flow_complete", "flow_id": "T-1"})
    assert isinstance(msg, FlowCompleteMessage)


def test_server_flow_failed_carries_error():
    """Verify a server `flow_failed` message carries the error text."""
    msg = _server(
        {"type": "flow_failed", "flow_id": "T-1", "error": "boom"}
    )
    assert isinstance(msg, FlowFailedMessage)
    assert msg.error == "boom"


def test_server_error_validates_without_flow_id():
    """Verify a server `error` message validates without flow_id."""
    msg = _server({"type": "error", "message": "bad json"})
    assert isinstance(msg, ErrorMessage)
    assert msg.message == "bad json"


def test_server_error_with_flow_id():
    """Verify a server `error` message accepts flow_id."""
    msg = _server({"type": "error", "flow_id": "T-1", "message": "oops"})
    assert isinstance(msg, ErrorMessage)
    assert msg.flow_id == "T-1"


def test_server_step_message_validates():
    """Verify a server `step` message validates."""
    msg = _server(
        {
            "type": "step",
            "flow_id": "T-1",
            "task": "build",
            "step": {
                "kind": "thinking",
                "timestamp": "2026-01-01T00:00:00Z",
                "text": "analyzing code",
            },
        }
    )
    assert isinstance(msg, StepMessage)
    assert msg.flow_id == "T-1"
    assert msg.task == "build"
    assert msg.step.kind == "thinking"


def test_step_message_dump():
    """Verify StepMessage.model_dump emits the expected type and step kind."""
    from app.schemas.log import IntermediateStep, StepKind

    step = IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
    msg = StepMessage(flow_id="f1", task="t1", step=step)
    dumped = msg.model_dump()
    assert dumped["type"] == "step"
    assert dumped["step"]["kind"] == "tool_call"


def test_run_message_dump_uses_snake_case():
    """Verify RunMessage.model_dump produces snake_case fields."""
    msg = RunMessage(
        flow_id="T-1", conduit_name="x", inputs={}, run_path="/abs"
    )
    dumped = msg.model_dump()
    assert dumped["type"] == "run"
    assert "flow_id" in dumped
    assert "conduit_name" in dumped
    assert "run_path" in dumped
