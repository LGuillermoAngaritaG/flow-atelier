"""WebSocket message envelopes for ``/ws/run-conduit`` (per SPEC §6).

Discriminated unions on ``type``. snake_case JSON in both directions.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from flow_atelier.schemas.log import IntermediateStep, LogEntry


class _WsBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------- client → server


class RunMessage(_WsBase):
    """Client tells the server to start a flow."""

    type: Literal["run"] = "run"
    conduit_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    run_path: str


class HitlAnswerMessage(_WsBase):
    """Client supplies HITL answers for a paused flow."""

    type: Literal["hitl_answer"] = "hitl_answer"
    flow_id: str
    answers: dict[str, Any] = Field(default_factory=dict)


class CancelMessage(_WsBase):
    """Client requests cancel of a running flow."""

    type: Literal["cancel"] = "cancel"
    flow_id: str


class ResumeMessage(_WsBase):
    """Client tells the server to resume a failed flow."""

    type: Literal["resume"] = "resume"
    flow_id: str


ClientMessage = Annotated[
    RunMessage | HitlAnswerMessage | CancelMessage | ResumeMessage,
    Field(discriminator="type"),
]


# ----------------------------------------------------------------- server → client


class StartedMessage(_WsBase):
    """Server signals that the flow has been registered and is starting."""

    type: Literal["started"] = "started"
    flow_id: str
    parent_flow_id: str | None = None
    parent_task: str | None = None
    conduit_name: str = ""


class LogMessage(_WsBase):
    """Server emits a log entry produced by a finished iteration."""

    type: Literal["log"] = "log"
    flow_id: str
    entry: LogEntry


class StepStatusMessage(_WsBase):
    """Server emits a per-step status transition."""

    type: Literal["step_status"] = "step_status"
    flow_id: str
    step: str
    status: str


class StepMessage(_WsBase):
    """Server emits an intermediate step from a running task."""

    type: Literal["step"] = "step"
    flow_id: str
    task: str
    step: IntermediateStep


class HitlRequestMessage(_WsBase):
    """Server requests human input for a paused HITL gate."""

    type: Literal["hitl_request"] = "hitl_request"
    flow_id: str
    inputs: list[dict[str, Any]] = Field(default_factory=list)


class FlowCompleteMessage(_WsBase):
    """Server signals flow finished successfully."""

    type: Literal["flow_complete"] = "flow_complete"
    flow_id: str


class FlowFailedMessage(_WsBase):
    """Server signals flow exited with an error."""

    type: Literal["flow_failed"] = "flow_failed"
    flow_id: str
    error: str = ""


class ErrorMessage(_WsBase):
    """Server signals a transport/parse error not bound to a flow."""

    type: Literal["error"] = "error"
    flow_id: str | None = None
    message: str


ServerMessage = Annotated[
    StartedMessage
    | LogMessage
    | StepStatusMessage
    | StepMessage
    | HitlRequestMessage
    | FlowCompleteMessage
    | FlowFailedMessage
    | ErrorMessage,
    Field(discriminator="type"),
]
