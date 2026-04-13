"""Log and execution result schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    """Primary result of a single executor invocation."""

    output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

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
    """Live notification emitted by the engine as each task iteration finishes.

    Passed to the optional ``on_task_event`` callback of :meth:`Engine.run`.
    Carries everything a renderer needs to display per-task progress without
    reaching into the store.
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
