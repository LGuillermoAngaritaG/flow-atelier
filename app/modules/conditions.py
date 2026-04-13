"""Conditional dependency parsing and evaluation.

Grammar:
    plain:        <task_name>
    match:        <task_name>.output.match(<regex>)
    not_match:    <task_name>.output.not_match(<regex>)

The regex is everything between the leftmost `(` after `.match(` / `.not_match(`
and the *last* `)` in the string — no quoting required.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Union

from app.schemas.progress import TaskStatus

_MATCH_MARKER = ".output.match("
_NOT_MATCH_MARKER = ".output.not_match("


@dataclass(frozen=True)
class PlainDependency:
    task: str


@dataclass
class ConditionalDependency:
    task: str
    pattern: str
    negate: bool
    _compiled: re.Pattern[str] | None = None

    def regex(self) -> re.Pattern[str]:
        """Return the compiled regex, caching it on first call.

        :returns: compiled :class:`re.Pattern`
        """
        if self._compiled is None:
            self._compiled = re.compile(self.pattern)
        return self._compiled


Dependency = Union[PlainDependency, ConditionalDependency]


class DependencyParseError(ValueError):
    """Raised when a dependency string cannot be parsed."""


def parse_dependency(dep: str) -> Dependency:
    """Parse one dependency string into a structured Dependency.

    Raises DependencyParseError on malformed syntax or invalid regex.
    """
    if not isinstance(dep, str) or not dep.strip():
        raise DependencyParseError(f"empty or non-string dependency: {dep!r}")

    # not_match first — it's a prefix of match semantically
    for marker, negate in ((_NOT_MATCH_MARKER, True), (_MATCH_MARKER, False)):
        idx = dep.find(marker)
        if idx == -1:
            continue
        task = dep[:idx]
        if not task or not task.replace("_", "").isalnum():
            raise DependencyParseError(f"invalid task name in dependency: {dep!r}")
        rest = dep[idx + len(marker):]
        if not rest.endswith(")"):
            raise DependencyParseError(
                f"dependency must end with ')': {dep!r}"
            )
        pattern = rest[:-1]
        try:
            re.compile(pattern)
        except re.error as e:
            raise DependencyParseError(
                f"invalid regex in dependency {dep!r}: {e}"
            ) from e
        return ConditionalDependency(task=task, pattern=pattern, negate=negate)

    # plain dependency — must be a bare task name
    if not dep.replace("_", "").isalnum():
        raise DependencyParseError(f"invalid dependency syntax: {dep!r}")
    return PlainDependency(task=dep)


def parse_dependencies(deps: list[str]) -> list[Dependency]:
    return [parse_dependency(d) for d in deps]


EvalResult = Literal["satisfied", "wait", "skip"]


def evaluate(
    dep: Dependency,
    statuses: dict[str, TaskStatus],
    outputs: dict[str, str],
) -> tuple[EvalResult, str | None]:
    """Evaluate a single dependency against current task state.

    Returns one of:
      ("satisfied", None)  — this dep is met
      ("wait", None)       — referenced task has not yet terminated
      ("skip", reason)     — this dep cannot be satisfied; dependent task must be skipped
    """
    status = statuses.get(dep.task)
    if status is None:
        return "skip", f"unknown task: {dep.task}"

    if status in (TaskStatus.pending, TaskStatus.running):
        return "wait", None

    if status in (TaskStatus.failed, TaskStatus.cancelled):
        return "skip", f"dependency {dep.task!r} ended with status {status.value}"

    if status == TaskStatus.skipped:
        return "skip", f"dependency {dep.task!r} was skipped"

    # status == completed
    if isinstance(dep, PlainDependency):
        return "satisfied", None

    assert isinstance(dep, ConditionalDependency)
    output = outputs.get(dep.task, "")
    match = dep.regex().search(output)
    ok = (match is None) if dep.negate else (match is not None)
    if ok:
        return "satisfied", None
    label = ".output.not_match" if dep.negate else ".output.match"
    return "skip", f"condition not met: {dep.task}{label}({dep.pattern})"
