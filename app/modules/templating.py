"""Template resolution for task prompts and inputs.

Supports four forms:
    {{inputs.<name>}}           — replaced with conduit/hitl input value
    {{<task_name>.output}}      — replaced with upstream task's output
    {{loop.previous}}           — this task's previous-iteration output
    {{loop.history}}            — all prior iterations of this task, numbered

Rules:
    - Missing `inputs.x`              -> TemplateError (immediate failure)
    - Reference to task not in outputs (or marked skipped/failed) -> SkipSignal
    - `loop.*` resolves to "" before the first iteration completes
"""
from __future__ import annotations

import re
from typing import Any

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _format_history(history: list[str], limit: int = 0) -> str:
    """Render prior loop iterations as numbered, separated blocks.

    :param history: outputs of completed iterations, oldest first.
    :param limit: max iterations to render, newest kept; <= 0 means all.
    :returns: numbered history string, or "" when no iterations have run.
    """
    omitted = 0
    shown = history
    if limit > 0 and len(history) > limit:
        omitted = len(history) - limit
        shown = history[-limit:]
    blocks = [
        f"--- iteration {i} ---\n{out}"
        for i, out in enumerate(shown, omitted + 1)
    ]
    if omitted:
        blocks.insert(0, f"--- {omitted} earlier iterations omitted ---")
    return "\n\n".join(blocks)


def extract_task_refs(template: str) -> set[str]:
    """Return the task names referenced as ``{{<task>.output}}`` in ``template``.

    ``inputs.*`` and ``loop.*`` expressions are not task references and are
    ignored. Used at validation time to reject references to unknown tasks
    before a flow starts.

    :param template: the raw task/template string to scan.
    :returns: set of referenced task names (may be empty).
    """
    refs: set[str] = set()
    for match in _TEMPLATE_RE.finditer(template):
        expr = match.group(1).strip()
        if expr.startswith("inputs.") or expr in ("loop.previous", "loop.history"):
            continue
        if expr.endswith(".output"):
            refs.add(expr[: -len(".output")])
    return refs


class TemplateError(ValueError):
    """Raised when a template cannot be resolved (hard failure)."""


class SkipSignal(Exception):
    """Raised when a template references a task that was skipped/failed.

    The engine catches this and marks the referencing task as skipped.
    """

    def __init__(self, reason: str):
        """Store the human-readable reason on the exception instance.

        :param reason: short explanation of why the skip was signalled.
        """
        super().__init__(reason)
        self.reason = reason


def resolve(
    template: str,
    inputs: dict[str, Any],
    task_outputs: dict[str, str],
    unavailable_tasks: set[str] | None = None,
    loop_history: list[str] | None = None,
    loop_history_limit: int = 0,
) -> str:
    """Resolve `{{...}}` expressions in ``template``.

    :param template: the template string
    :param inputs: mapping of input name -> value
    :param task_outputs: mapping of task name -> completed output string
    :param unavailable_tasks: names of tasks whose outputs cannot be used
        (skipped / failed / cancelled)
    :param loop_history: this task's prior-iteration outputs, oldest first,
        backing ``{{loop.previous}}`` and ``{{loop.history}}``
    :param loop_history_limit: max iterations ``{{loop.history}}`` renders,
        newest kept; <= 0 means unlimited
    :raises TemplateError: missing input or unknown identifier
    :raises SkipSignal: reference to a skipped/failed task output
    """
    unavailable = unavailable_tasks or set()
    history = loop_history or []

    def _sub(match: re.Match[str]) -> str:
        """Replace a single ``{{...}}`` occurrence with its resolved value.

        :param match: regex match for one template expression.
        :returns: the resolved replacement string.
        """
        expr = match.group(1).strip()
        if expr.startswith("inputs."):
            key = expr[len("inputs."):]
            if key not in inputs:
                raise TemplateError(f"missing input: {key!r}")
            return str(inputs[key])
        if expr == "loop.previous":
            return history[-1] if history else ""
        if expr == "loop.history":
            return _format_history(history, loop_history_limit)
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
