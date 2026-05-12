"""Log and execution result schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.progress import TaskStatus


class StepKind(str, Enum):
    thinking = "thinking"
    tool_call = "tool_call"
    tool_result = "tool_result"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``.

    :returns: current UTC timestamp formatted as ISO 8601 with ``Z`` suffix.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class IntermediateStep(BaseModel):
    """One intermediate step captured during execution."""

    kind: StepKind
    timestamp: str = Field(default_factory=_now_iso)
    # thinking
    text: str = ""
    # tool_call / tool_result
    tool_call_id: str = ""
    tool_name: str = ""
    tool_kind: str = ""
    tool_status: str = ""
    tool_input: str = ""
    tool_output: str = ""
    locations: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Primary result of a single executor invocation."""

    output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    sub_outputs: list[str] = Field(default_factory=list)
    """Per-sub-task outputs from a nested conduit's child flow.

    Populated only by :class:`ConduitExecutor`; every other executor
    leaves this empty. The engine reads this field exclusively for
    ``tool:conduit`` tasks when evaluating the per-iteration loop
    predicate.
    """
    last_turn_output: str | None = None
    """Text emitted by the agent on the final turn only, for interactive
    harness tasks. When set, the engine uses it instead of ``output`` when
    populating ``outputs[task]`` (which feeds ``{{task.output}}`` template
    resolution and ``outputs.yaml``). ``None`` for every other executor;
    engine falls back to ``output`` in that case.
    """
    steps: list[IntermediateStep] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether the execution finished with a zero exit code.

        :returns: ``True`` if ``exit_code`` is ``0``, otherwise ``False``.
        """
        return self.exit_code == 0


class LogEntry(BaseModel):
    """One entry in the flow's logs.json."""

    task: str
    tool: str
    iteration: int = 1
    of: int = 1
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output: str = ""
    started_at: str
    finished_at: str
    duration_seconds: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)
    steps: list[IntermediateStep] = Field(default_factory=list)


class TaskEvent(BaseModel):
    """Live notification emitted by the engine as a task transitions.

    Passed to the optional ``on_task_event`` callback of :meth:`Engine.run`.
    Carries everything a renderer needs to display per-task progress without
    reaching into the store.

    Events fire on every task disposition, not just completed iterations:
    ``status`` distinguishes ``completed`` / ``failed`` / ``skipped`` /
    ``cancelled`` so renderers can show skipped & cancelled tasks instead of
    silently dropping them.
    """

    task: str
    tool: str
    iteration: int = 1
    of: int = 1
    exit_code: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    stdout: str = ""
    stderr: str = ""
    success: bool = True
    status: TaskStatus = TaskStatus.completed
    reason: str = ""
    live_streamed: bool = False
    steps: list[IntermediateStep] = Field(default_factory=list)
