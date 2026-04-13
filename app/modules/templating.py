"""Template resolution for task prompts and inputs.

Supports two forms:
    {{inputs.<name>}}           — replaced with conduit/hitl input value
    {{<task_name>.output}}      — replaced with upstream task's output

Rules:
    - Missing `inputs.x`              -> TemplateError (immediate failure)
    - Reference to task not in outputs (or marked skipped/failed) -> SkipSignal
"""
from __future__ import annotations

import re
from typing import Any

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


class TemplateError(ValueError):
    """Raised when a template cannot be resolved (hard failure)."""


class SkipSignal(Exception):
    """Raised when a template references a task that was skipped/failed.

    The engine catches this and marks the referencing task as skipped.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def resolve(
    template: str,
    inputs: dict[str, Any],
    task_outputs: dict[str, str],
    unavailable_tasks: set[str] | None = None,
) -> str:
    """Resolve `{{...}}` expressions in ``template``.

    :param template: the template string
    :param inputs: mapping of input name -> value
    :param task_outputs: mapping of task name -> completed output string
    :param unavailable_tasks: names of tasks whose outputs cannot be used
        (skipped / failed / cancelled)
    :raises TemplateError: missing input or unknown identifier
    :raises SkipSignal: reference to a skipped/failed task output
    """
    unavailable = unavailable_tasks or set()

    def _sub(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        if expr.startswith("inputs."):
            key = expr[len("inputs."):]
            if key not in inputs:
                raise TemplateError(f"missing input: {key!r}")
            return str(inputs[key])
        if expr.endswith(".output"):
            task = expr[: -len(".output")]
            if task in unavailable:
                raise SkipSignal(
                    f"references output of unavailable task {task!r}"
                )
            if task not in task_outputs:
                raise SkipSignal(
                    f"references output of task {task!r} which has not completed"
                )
            return task_outputs[task]
        raise TemplateError(f"unknown template expression: {expr!r}")

    return _TEMPLATE_RE.sub(_sub, template)
