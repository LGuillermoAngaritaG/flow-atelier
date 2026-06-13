"""Conduit and task schemas."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
# Conduit names become a single filesystem path component (conduits/<name>/),
# so they must reject "/", ".", ".." to prevent path traversal on write/delete.
# Hyphens are allowed because real conduits on disk use them (autonomous-projects).
_CONDUIT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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


class InputSpec(BaseModel):
    """A declared conduit input: a description and an optional default.

    When ``default`` is set, the input is optional — callers that omit it get
    the default; callers that supply it override it.
    """

    description: str = ""
    default: str | None = None


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
    on_exhaust: Literal["complete", "fail"] = "complete"
    stagnation_limit: int | None = None
    interactive: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_valid(cls, v: str) -> str:
        """Restrict task names to the grammar shared by deps and templating.

        :param v: the proposed task name.
        :returns: the validated name unchanged.
        """
        if not _TASK_NAME_RE.match(v):
            raise ValueError(
                f"invalid task name {v!r}: only letters, digits and "
                "underscores are allowed"
            )
        return v

    @field_validator("repeat")
    @classmethod
    def _repeat_positive(cls, v: int) -> int:
        """Ensure ``repeat`` is at least one iteration.

        :param v: the proposed ``repeat`` value.
        :returns: the validated ``repeat`` value unchanged.
        """
        if v < 1:
            raise ValueError("repeat must be >= 1")
        return v

    @model_validator(mode="after")
    def _validate_loop_predicates(self) -> TaskDefinition:
        """Validate ``until``/``while`` mutual exclusion and predicate syntax.

        :returns: the validated ``TaskDefinition`` instance.
        """
        if self.until is not None and self.while_ is not None:
            raise ValueError(
                "until and while are mutually exclusive — set only one"
            )
        if (
            self.on_exhaust != "complete"
            and self.until is None
            and self.while_ is None
        ):
            raise ValueError("on_exhaust requires until or while")
        if self.stagnation_limit is not None:
            if self.repeat <= 1:
                raise ValueError("stagnation_limit requires repeat > 1")
            if self.stagnation_limit < 2:
                raise ValueError("stagnation_limit must be >= 2")
        for field_name, expr in (("until", self.until), ("while", self.while_)):
            if expr is None:
                continue
            if self.repeat <= 1:
                raise ValueError(
                    f"{field_name} requires repeat > 1 "
                    "(single iteration can't early-exit)"
                )
            # Local import to avoid a schemas → modules dependency at import time.
            from flow_atelier.modules.conditions import DependencyParseError, parse_output_predicate

            try:
                parse_output_predicate(expr)
            except DependencyParseError as e:
                raise ValueError(str(e)) from e
        return self


class Conduit(BaseModel):
    """A reusable workflow definition."""

    name: str
    description: str
    timeout: int = Field(default=3600, ge=1)
    max_concurrency: int = Field(default=3, ge=1)
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    tasks: list[TaskDefinition]

    @field_validator("name")
    @classmethod
    def _name_valid(cls, v: str) -> str:
        """Restrict conduit names to a safe single filesystem path component.

        :param v: the proposed conduit name.
        :returns: the validated name unchanged.
        """
        if not _CONDUIT_NAME_RE.match(v):
            raise ValueError(
                f"invalid conduit name {v!r}: only letters, digits, "
                "underscores and hyphens are allowed"
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def _normalize_tasks(cls, data: Any) -> Any:
        """Accept YAML's list-of-single-key-dicts form for tasks, and the
        plain-string shorthand for inputs.

        :param data: raw input passed to the model; only ``dict`` payloads are normalized.
        :returns: ``data`` with its ``tasks`` list flattened into plain task dicts
            and its ``inputs`` values coerced to ``InputSpec`` mappings.
        """
        if not isinstance(data, dict):
            return data
        raw_inputs = data.get("inputs")
        if isinstance(raw_inputs, dict):
            data["inputs"] = {
                key: {"description": value} if isinstance(value, str) else value
                for key, value in raw_inputs.items()
            }
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
    def _validate_unique_task_names(self) -> Conduit:
        """Ensure no two tasks in the conduit share the same ``name``.

        :returns: the validated ``Conduit`` instance.
        """
        names = [t.name for t in self.tasks]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate task names: {dupes}")
        return self
