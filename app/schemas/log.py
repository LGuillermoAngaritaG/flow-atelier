"""Log and execution result schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.progress import TaskStatus


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

    @property
    def success(self) -> bool:
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
