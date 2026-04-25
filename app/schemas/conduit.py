"""Conduit and task schemas."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ToolType(str, Enum):
    bash = "tool:bash"
    hitl = "tool:hitl"
    conduit = "tool:conduit"
    claude = "harness:claude-code"
    codex = "harness:codex"
    opencode = "harness:opencode"
    copilot = "harness:copilot"
    cursor = "harness:cursor"


class HitlInput(BaseModel):
    """A single named input for a tool:hitl task."""

    name: str
    description: str


class TaskDefinition(BaseModel):
    """A single task within a conduit."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    task: str
    tool: ToolType
    depends_on: list[str] = Field(default_factory=list)
    repeat: int = 1
    until: str | None = None
    while_: str | None = Field(default=None, alias="while")
    interactive: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("repeat")
    @classmethod
    def _repeat_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("repeat must be >= 1")
        return v

    @model_validator(mode="after")
    def _validate_loop_predicates(self) -> "TaskDefinition":
        if self.until is not None and self.while_ is not None:
            raise ValueError(
                "until and while are mutually exclusive — set only one"
            )
        for field_name, expr in (("until", self.until), ("while", self.while_)):
            if expr is None:
                continue
            if self.repeat <= 1:
                raise ValueError(
                    f"{field_name} requires repeat > 1 "
                    "(single iteration can't early-exit)"
                )
            # Local import to avoid a schemas → modules dependency at import time.
            from app.modules.conditions import DependencyParseError, parse_output_predicate

            try:
                parse_output_predicate(expr)
            except DependencyParseError as e:
                raise ValueError(str(e)) from e
        return self


class Conduit(BaseModel):
    """A reusable workflow definition."""

    name: str
    description: str
    timeout: int = 3600
    max_concurrency: int = 3
    inputs: dict[str, str] = Field(default_factory=dict)
    tasks: list[TaskDefinition]

    @model_validator(mode="before")
    @classmethod
    def _normalize_tasks(cls, data: Any) -> Any:
        """Accept YAML's list-of-single-key-dicts form for tasks."""
        if not isinstance(data, dict):
            return data
        raw_tasks = data.get("tasks")
        if not isinstance(raw_tasks, list):
            return data
        normalized: list[dict[str, Any]] = []
        for item in raw_tasks:
            if isinstance(item, dict) and len(item) == 1:
                key = next(iter(item))
                value = item[key]
                if isinstance(value, dict) and "name" not in value:
                    value = {"name": key, **value}
                normalized.append(value)
            else:
                normalized.append(item)
        data["tasks"] = normalized
        return data

    @model_validator(mode="after")
    def _validate_unique_task_names(self) -> "Conduit":
        names = [t.name for t in self.tasks]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate task names: {dupes}")
        return self
