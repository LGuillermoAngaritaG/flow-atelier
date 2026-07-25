"""Conditional dependency parsing and evaluation.

Grammar:
    plain:        <task_name>
    match:        <task_name>.output.match(<regex>)
    not_match:    <task_name>.output.not_match(<regex>)

The regex is everything between the leftmost `(` after `.match(` / `.not_match(`
and the *last* `)` in the string. Quotes around the regex are optional and are
stripped when present, so `match(PASS)` and `match("PASS")` are equivalent (see
:func:`strip_surrounding_quotes`).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

from flow_atelier.schemas.conduit import _TASK_NAME_RE
from flow_atelier.schemas.progress import TaskStatus

_MATCH_MARKER = ".output.match("
_NOT_MATCH_MARKER = ".output.not_match("

_OUTPUT_MATCH_PREFIX = "output.match("
_OUTPUT_NOT_MATCH_PREFIX = "output.not_match("

_QUOTE_CHARS = ('"', "'")


def strip_surrounding_quotes(pattern: str) -> str:
    """Drop one matching pair of wrapping quotes from a match pattern.

    The DSL takes everything between the parentheses as the regex, so a quoted
    ``output.match("PASS")`` would otherwise search for a literal ``"PASS"``
    *including* the quotes and silently never match — a loop just runs every
    iteration instead of breaking early. Authors write the quotes anyway
    (they read like a string literal), so accept both spellings.

    To match a real quote character, escape it: ``\\"PASS\\"`` is left alone and
    still matches ``"PASS"`` with quotes. An empty body (``""``) is also left
    alone, since stripping it would turn a literal into a match-everything
    regex.

    :param pattern: raw regex source extracted from between the parentheses.
    :returns: the pattern without one wrapping quote pair.
    """
    if (
        len(pattern) > 2
        and pattern[0] in _QUOTE_CHARS
        and pattern[-1] == pattern[0]
        and pattern[-2] != "\\"
    ):
        return pattern[1:-1]
    return pattern


# Task names share the schema grammar: ``_TASK_NAME_RE`` is imported from
# schemas.conduit so the two validators can't drift apart. ``.isalnum()`` would
# also accept Unicode letters/digits, so a dependency string could be accepted
# that no schema-valid task name could ever match.

# Author regexes are matched against task/agent output. Bounding the candidate
# length caps the work an adversarial *output* (matched by an otherwise-benign
# author regex) can impose before matching.
MATCH_INPUT_CHAR_CAP = 1_000_000


async def _search_off_loop(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """Run ``pattern.search`` on a worker thread, off the event loop.

    Author regexes evaluate against agent/bash output while the engine runs
    flows concurrently on one event loop. A catastrophic-backtracking pattern
    (or a benign pattern against adversarial output) is CPU-bound and would
    otherwise block every concurrent flow, HITL prompt, and WS send for its
    whole duration. Running it via :func:`asyncio.to_thread` keeps the loop
    responsive; the input is first capped at :data:`MATCH_INPUT_CHAR_CAP`.

    :param pattern: compiled regex to evaluate.
    :param text: candidate output (truncated before matching).
    :returns: the :class:`re.Match` or ``None``.
    """
    return await asyncio.to_thread(pattern.search, text[:MATCH_INPUT_CHAR_CAP])


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


Dependency = PlainDependency | ConditionalDependency


class DependencyParseError(ValueError):
    """Raised when a dependency string cannot be parsed."""


def parse_dependency(dep: str) -> Dependency:
    """Parse one dependency string into a structured Dependency.

    Raises DependencyParseError on malformed syntax or invalid regex.

    :param dep: raw dependency string from the conduit definition.
    """
    if not isinstance(dep, str) or not dep.strip():
        raise DependencyParseError(f"empty or non-string dependency: {dep!r}")

    # not_match first — it's a prefix of match semantically
    for marker, negate in ((_NOT_MATCH_MARKER, True), (_MATCH_MARKER, False)):
        idx = dep.find(marker)
        if idx == -1:
            continue
        task = dep[:idx]
        if not _TASK_NAME_RE.match(task):
            raise DependencyParseError(f"invalid task name in dependency: {dep!r}")
        rest = dep[idx + len(marker):]
        if not rest.endswith(")"):
            raise DependencyParseError(
                f"dependency must end with ')': {dep!r}"
            )
        pattern = strip_surrounding_quotes(rest[:-1])
        try:
            re.compile(pattern)
        except re.error as e:
            raise DependencyParseError(
                f"invalid regex in dependency {dep!r}: {e}"
            ) from e
        return ConditionalDependency(task=task, pattern=pattern, negate=negate)

    # plain dependency — must be a bare task name
    if not _TASK_NAME_RE.match(dep):
        raise DependencyParseError(f"invalid dependency syntax: {dep!r}")
    return PlainDependency(task=dep)


def parse_dependencies(deps: list[str]) -> list[Dependency]:
    """Parse a list of dependency strings into structured Dependency objects.

    :param deps: list of raw dependency strings.
    :returns: list of parsed :class:`Dependency` values, in input order.
    """
    return [parse_dependency(d) for d in deps]


def sink_task_names(conduit) -> list[str]:
    """Return the conduit's sink tasks (no other task depends on them).

    :param conduit: parsed :class:`app.schemas.conduit.Conduit`.
    :returns: sink task names in conduit definition order.
    """
    targeted = {
        d.task
        for t in conduit.tasks
        for d in parse_dependencies(t.depends_on)
    }
    return [t.name for t in conduit.tasks if t.name not in targeted]


def parse_output_predicate(expr: str) -> tuple[re.Pattern[str], bool]:
    """Parse a ``until``-style predicate against the current task's output.

    Accepts ``output.match(<regex>)`` (returns ``negate=False``) or
    ``output.not_match(<regex>)`` (returns ``negate=True``). The regex is
    everything between the prefix's ``(`` and the final ``)`` — the same
    delimiting rule as :func:`parse_dependency`.

    :param expr: raw predicate string from the conduit definition.
    :raises DependencyParseError: malformed DSL or uncompilable regex
    """
    if not isinstance(expr, str) or not expr.strip():
        raise DependencyParseError(f"empty or non-string predicate: {expr!r}")

    for prefix, negate in (
        (_OUTPUT_NOT_MATCH_PREFIX, True),
        (_OUTPUT_MATCH_PREFIX, False),
    ):
        if expr.startswith(prefix):
            rest = expr[len(prefix):]
            if not rest.endswith(")"):
                raise DependencyParseError(
                    f"predicate must end with ')': {expr!r}"
                )
            pattern = strip_surrounding_quotes(rest[:-1])
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                raise DependencyParseError(
                    f"invalid regex in predicate {expr!r}: {e}"
                ) from e
            return compiled, negate

    raise DependencyParseError(
        f"predicate must start with 'output.match(' or 'output.not_match(': {expr!r}"
    )


LoopMode = Literal["until", "while"]


async def evaluate_loop_predicate(
    predicate: tuple[re.Pattern[str], bool],
    outputs: list[str],
    mode: LoopMode,
) -> bool:
    """Decide whether a per-task loop should break at this iteration.

    Returns True if the loop should stop now. ``outputs`` carries one
    entry per nested sub-task output for conduit scope, or
    ``[result.output]`` for simple tasks. ``predicate`` is the
    ``(compiled_regex, negate)`` tuple produced by
    :func:`parse_output_predicate`.

    Truth table (any-match = at least one output matches the un-negated
    regex; every-match = all outputs match):

    - ``mode="until"`` + non-negated: break iff any-match.
    - ``mode="until"`` + negated:     break iff not any-match.
    - ``mode="while"`` + non-negated: break iff not any-match.
    - ``mode="while"`` + negated:     break iff every-match.

    An empty ``outputs`` list never breaks — wait for data on the next
    iteration.

    :param predicate: ``(compiled_regex, negate)`` from :func:`parse_output_predicate`.
    :param outputs: per-sub-task outputs (or ``[result.output]`` for simple tasks).
    :param mode: ``"until"`` or ``"while"`` loop semantics.
    :returns: ``True`` when the loop should stop now, ``False`` otherwise.
    """
    if mode not in ("until", "while"):
        raise ValueError(f"unknown loop mode: {mode!r}")
    if not outputs:
        return False
    pattern, negate = predicate
    matches = [
        (await _search_off_loop(pattern, out)) is not None for out in outputs
    ]
    any_match = any(matches)
    if mode == "until":
        return (not any_match) if negate else any_match
    # mode == "while"
    return all(matches) if negate else (not any_match)


EvalResult = Literal["satisfied", "wait", "skip"]


async def evaluate(
    dep: Dependency,
    statuses: dict[str, TaskStatus],
    outputs: dict[str, str],
) -> tuple[EvalResult, str | None]:
    """Evaluate a single dependency against current task state.

    Returns one of:
      ("satisfied", None)  — this dep is met
      ("wait", None)       — referenced task has not yet terminated
      ("skip", reason)     — this dep cannot be satisfied; dependent task must be skipped

    :param dep: parsed dependency to evaluate.
    :param statuses: current map of task name to :class:`TaskStatus`.
    :param outputs: completed task outputs keyed by task name.
    :returns: tuple of ``(EvalResult, optional reason)``.
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
    match = await _search_off_loop(dep.regex(), output)
    ok = (match is None) if dep.negate else (match is not None)
    if ok:
        return "satisfied", None
    label = ".output.not_match" if dep.negate else ".output.match"
    return "skip", f"condition not met: {dep.task}{label}({dep.pattern})"
