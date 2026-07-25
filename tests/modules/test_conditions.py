"""Unit tests for the conditions module."""
import asyncio
import time

import pytest

from flow_atelier.modules.conditions import (
    ConditionalDependency,
    DependencyParseError,
    PlainDependency,
    evaluate,
    parse_dependency,
)
from flow_atelier.schemas.progress import TaskStatus


def test_parse_plain():
    """Verify parse_dependency() returns a PlainDependency for bare task names."""
    dep = parse_dependency("clone_repo")
    assert isinstance(dep, PlainDependency)
    assert dep.task == "clone_repo"


def test_parse_match():
    """Verify parse_dependency() parses an output.match(...) conditional."""
    dep = parse_dependency("review.output.match(VERDICT:\\s*APPROVE)")
    assert isinstance(dep, ConditionalDependency)
    assert dep.task == "review"
    assert dep.negate is False
    assert dep.pattern == "VERDICT:\\s*APPROVE"


def test_parse_not_match():
    """Verify parse_dependency() parses an output.not_match(...) conditional."""
    dep = parse_dependency("review.output.not_match(VERDICT:\\s*APPROVE)")
    assert isinstance(dep, ConditionalDependency)
    assert dep.negate is True


def test_parse_regex_with_inner_parens():
    """Verify parse_dependency() preserves inner parens in the regex pattern."""
    # final closing paren delimits; inner `)` is part of the regex
    dep = parse_dependency("x.output.match(foo(bar))")
    assert isinstance(dep, ConditionalDependency)
    assert dep.pattern == "foo(bar)"


def test_parse_invalid_regex():
    """Verify parse_dependency() rejects an invalid regex."""
    with pytest.raises(DependencyParseError):
        parse_dependency("x.output.match([unclosed)")


def test_parse_missing_close_paren():
    """Verify parse_dependency() rejects a missing close paren."""
    with pytest.raises(DependencyParseError):
        parse_dependency("x.output.match(foo")


def test_parse_empty():
    """Verify parse_dependency() rejects the empty string."""
    with pytest.raises(DependencyParseError):
        parse_dependency("")


def test_parse_plain_rejects_unicode_name():
    """Verify a plain dependency with a Unicode name is rejected.

    ``str.isalnum()`` would accept ``café``, but no schema-valid task name
    (ASCII ``[A-Za-z0-9_]+``) could ever match it, so it must be rejected.
    """
    with pytest.raises(DependencyParseError):
        parse_dependency("café")


def test_parse_conditional_rejects_unicode_task_name():
    """Verify a conditional dependency with a Unicode task name is rejected."""
    with pytest.raises(DependencyParseError):
        parse_dependency("café.output.match(ok)")


async def test_evaluate_plain_completed():
    """Verify evaluate() returns satisfied for a completed plain dep."""
    dep = parse_dependency("a")
    status = {"a": TaskStatus.completed}
    assert await evaluate(dep, status, {"a": "ok"}) == ("satisfied", None)


async def test_evaluate_plain_running():
    """Verify evaluate() returns wait for a running plain dep."""
    dep = parse_dependency("a")
    assert await evaluate(dep, {"a": TaskStatus.running}, {}) == ("wait", None)


async def test_evaluate_plain_failed():
    """Verify evaluate() returns skip with a 'failed' reason for failed dep."""
    dep = parse_dependency("a")
    result, reason = await evaluate(dep, {"a": TaskStatus.failed}, {})
    assert result == "skip"
    assert "failed" in reason


async def test_evaluate_plain_skipped():
    """Verify evaluate() returns skip with a 'skipped' reason for skipped dep."""
    dep = parse_dependency("a")
    result, reason = await evaluate(dep, {"a": TaskStatus.skipped}, {})
    assert result == "skip"
    assert "skipped" in reason


async def test_evaluate_conditional_match_satisfied():
    """Verify evaluate() returns satisfied when the match pattern hits."""
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    assert await evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "blah\nVERDICT: APPROVE\n"},
    ) == ("satisfied", None)


async def test_evaluate_conditional_match_not_met_skips():
    """Verify evaluate() skips when the match pattern is absent."""
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    result, reason = await evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "VERDICT: REJECT"},
    )
    assert result == "skip"
    assert "condition not met" in reason


async def test_evaluate_not_match_satisfied():
    """Verify evaluate() returns satisfied when the not_match pattern is absent."""
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    assert await evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "all good"},
    ) == ("satisfied", None)


async def test_evaluate_not_match_triggers_skip():
    """Verify evaluate() skips when not_match pattern is present."""
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    result, _ = await evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "CRITICAL vuln"},
    )
    assert result == "skip"


async def test_evaluate_unknown_task_skips():
    """Verify evaluate() skips when the dependency target is unknown."""
    dep = parse_dependency("ghost")
    result, reason = await evaluate(dep, {"a": TaskStatus.completed}, {})
    assert result == "skip"
    assert "unknown" in reason


# ---------------------------------------------------------------- output predicate


def test_parse_output_predicate_match():
    """Verify parse_output_predicate() parses output.match(...) expressions."""
    from flow_atelier.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.match(DONE)")
    assert pattern.search("foo DONE bar")
    assert not pattern.search("nope")
    assert negate is False


def test_parse_output_predicate_not_match():
    """Verify parse_output_predicate() parses output.not_match(...) expressions."""
    from flow_atelier.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.not_match(RETRY)")
    assert pattern.search("RETRY now")
    assert negate is True


def test_parse_output_predicate_inner_parens():
    """Verify parse_output_predicate() preserves inner parens."""
    from flow_atelier.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.match(foo(bar))")
    assert pattern.pattern == "foo(bar)"
    assert negate is False


def test_parse_output_predicate_bare_regex_rejected():
    """Verify parse_output_predicate() rejects bare regex expressions."""
    from flow_atelier.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("DONE")


def test_parse_output_predicate_invalid_regex_rejected():
    """Verify parse_output_predicate() rejects an invalid regex."""
    from flow_atelier.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("output.match([unclosed)")


def test_parse_output_predicate_missing_close_paren():
    """Verify parse_output_predicate() rejects missing close paren."""
    from flow_atelier.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("output.match(foo")


def test_parse_output_predicate_empty_rejected():
    """Verify parse_output_predicate() rejects the empty string."""
    from flow_atelier.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("")


# ------------------------------------------------------------------ evaluate_loop_predicate


def _pred(expr: str):
    """Build a parsed output predicate for tests.

    :param expr: predicate expression to parse.
    """
    from flow_atelier.modules.conditions import parse_output_predicate

    return parse_output_predicate(expr)


@pytest.mark.parametrize(
    "expr,outputs,expected",
    [
        # mode="until", non-negated: break iff any output matches
        ("output.match(DONE)", ["wait"], False),
        ("output.match(DONE)", ["DONE"], True),
        ("output.match(DONE)", ["wait", "still", "DONE finally"], True),
        ("output.match(DONE)", ["wait", "still"], False),
        # mode="until", negated (.not_match): break iff no output matches the un-negated regex
        ("output.not_match(RETRY)", ["RETRY"], False),
        ("output.not_match(RETRY)", ["clean"], True),
        ("output.not_match(RETRY)", ["RETRY", "RETRY"], False),
        ("output.not_match(RETRY)", ["clean", "also clean"], True),
        ("output.not_match(RETRY)", ["RETRY", "clean"], False),
    ],
)
async def test_evaluate_loop_predicate_until(expr, outputs, expected):
    """Verify evaluate_loop_predicate() in until mode for parametrized cases.

    :param expr: predicate expression under test.
    :param outputs: list of task outputs to evaluate against.
    :param expected: expected boolean result.
    """
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert await evaluate_loop_predicate(_pred(expr), outputs, "until") is expected


@pytest.mark.parametrize(
    "expr,outputs,expected",
    [
        # mode="while", non-negated: break iff no output matches
        ("output.match(retry)", ["retry"], False),
        ("output.match(retry)", ["done"], True),
        ("output.match(retry)", ["retry", "retry"], False),
        ("output.match(retry)", ["done", "ready"], True),
        ("output.match(retry)", ["done", "retry"], False),
        # mode="while", negated: break iff every output matches the un-negated regex
        ("output.not_match(ready)", ["pending"], False),
        ("output.not_match(ready)", ["ready"], True),
        ("output.not_match(ready)", ["ready", "ready"], True),
        ("output.not_match(ready)", ["ready", "pending"], False),
    ],
)
async def test_evaluate_loop_predicate_while(expr, outputs, expected):
    """Verify evaluate_loop_predicate() in while mode for parametrized cases.

    :param expr: predicate expression under test.
    :param outputs: list of task outputs to evaluate against.
    :param expected: expected boolean result.
    """
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert await evaluate_loop_predicate(_pred(expr), outputs, "while") is expected


async def test_evaluate_loop_predicate_empty_outputs_does_not_break():
    """Verify evaluate_loop_predicate() returns False on empty outputs."""
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert await evaluate_loop_predicate(_pred("output.match(x)"), [], "until") is False
    assert await evaluate_loop_predicate(_pred("output.match(x)"), [], "while") is False
    assert (
        await evaluate_loop_predicate(_pred("output.not_match(x)"), [], "until") is False
    )
    assert (
        await evaluate_loop_predicate(_pred("output.not_match(x)"), [], "while") is False
    )


async def test_evaluate_loop_predicate_invalid_mode_raises():
    """Verify evaluate_loop_predicate() raises on an unknown mode."""
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    with pytest.raises(ValueError):
        await evaluate_loop_predicate(_pred("output.match(x)"), ["x"], "forever")  # type: ignore[arg-type]


async def test_evaluate_loop_predicate_truncates_oversized_output():
    """Verify the matcher only sees the first MATCH_INPUT_CHAR_CAP chars.

    A pattern anchored past the cap must not match, so an adversarial output
    cannot force unbounded matching work on the shared event loop.
    """
    from flow_atelier.modules.conditions import (
        MATCH_INPUT_CHAR_CAP,
        evaluate_loop_predicate,
    )

    beyond_cap = "a" * MATCH_INPUT_CHAR_CAP + "DONE"
    assert (
        await evaluate_loop_predicate(
            _pred("output.match(DONE)"), [beyond_cap], "until"
        )
        is False
    )
    within_cap = "DONE" + "a" * 10
    assert (
        await evaluate_loop_predicate(
            _pred("output.match(DONE)"), [within_cap], "until"
        )
        is True
    )


async def test_evaluate_conditional_dep_truncates_oversized_output():
    """Verify evaluate() bounds the candidate output before matching."""
    from flow_atelier.modules.conditions import MATCH_INPUT_CHAR_CAP

    dep = parse_dependency("a.output.match(DONE)")
    statuses = {"a": TaskStatus.completed}
    beyond_cap = "a" * MATCH_INPUT_CHAR_CAP + "DONE"
    result, _ = await evaluate(dep, statuses, {"a": beyond_cap})
    assert result == "skip"


async def test_loop_predicate_match_runs_off_event_loop():
    """A slow (CPU-bound) regex match must not block concurrent coroutines.

    The matcher runs via ``asyncio.to_thread``, so a search that blocks its
    worker thread leaves the event loop free: a concurrent ticker keeps
    advancing. If the search ran inline on the loop, the ticker would be
    frozen for the whole match and barely advance.
    """
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    class _BlockingPattern:
        def search(self, _text: str):
            # Stand-in for a catastrophic-backtracking match: blocks the
            # calling thread (not the event loop) for a fixed duration.
            time.sleep(0.2)
            return None

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(40):
            await asyncio.sleep(0.005)
            ticks += 1

    tick_task = asyncio.create_task(ticker())
    try:
        result = await evaluate_loop_predicate((_BlockingPattern(), False), ["x"], "until")
    finally:
        tick_task.cancel()

    assert result is False
    # ~0.2s of off-loop matching at one tick per 5ms -> well over 10 ticks.
    assert ticks >= 10


def test_sink_task_names_returns_undepended_tasks_in_order():
    """Verify sink_task_names returns tasks nothing depends on, in definition
    order, counting conditional dependency targets as depended-upon."""
    from flow_atelier.modules.conditions import sink_task_names
    from flow_atelier.schemas.conduit import Conduit

    conduit = Conduit.model_validate(
        {
            "name": "c",
            "description": "d",
            "tasks": [
                {"a": {"description": "d", "task": "x", "tool": "tool:bash",
                       "depends_on": []}},
                {"b": {"description": "d", "task": "x", "tool": "tool:bash",
                       "depends_on": ["a.output.match(ok)"]}},
                {"c": {"description": "d", "task": "x", "tool": "tool:bash",
                       "depends_on": ["a"]}},
            ],
        }
    )
    assert sink_task_names(conduit) == ["b", "c"]



# ------------------------------------------------------- quote stripping


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"PASS"', "PASS"),
        ("'PASS'", "PASS"),
        ("PASS", "PASS"),
        ('"^429$"', "^429$"),
        ('"a|b"', "a|b"),
        # Mismatched or partial quotes are part of the regex, not a wrapper.
        ('"PASS', '"PASS'),
        ('PASS"', 'PASS"'),
        ("\"PASS'", "\"PASS'"),
        # Escaped trailing quote means the author wants a literal quote.
        ('\\"PASS\\"', '\\"PASS\\"'),
        # Too short to be a wrapper, and stripping "" would match everything.
        ('""', '""'),
        ('"', '"'),
        ("", ""),
    ],
)
def test_strip_surrounding_quotes(raw, expected):
    """Verify only a genuine wrapping quote pair is removed.

    :param raw: pattern as written between the parentheses.
    :param expected: pattern the engine should compile.
    """
    from flow_atelier.modules.conditions import strip_surrounding_quotes

    assert strip_surrounding_quotes(raw) == expected


def test_quoted_dependency_regex_matches_unquoted_output():
    """`a.output.match("PASS")` must match plain `PASS`, not a literal `"PASS"`."""
    dep = parse_dependency('a.output.match("PASS")')

    assert isinstance(dep, ConditionalDependency)
    assert dep.pattern == "PASS"
    assert dep.regex().search("tests: PASS") is not None


def test_quoted_and_unquoted_predicates_are_equivalent():
    """Both spellings of an `until` predicate compile to the same regex."""
    from flow_atelier.modules.conditions import parse_output_predicate

    quoted, negate_q = parse_output_predicate('output.match("PASS")')
    bare, negate_b = parse_output_predicate("output.match(PASS)")

    assert quoted.pattern == bare.pattern == "PASS"
    assert negate_q is negate_b is False
    assert quoted.search("all tests PASS") is not None


def test_escaped_quotes_still_match_a_literal_quoted_string():
    """The escape hatch: `\\"PASS\\"` keeps matching output that has real quotes."""
    from flow_atelier.modules.conditions import parse_output_predicate

    compiled, _ = parse_output_predicate('output.match(\\"PASS\\")')

    assert compiled.search('result: "PASS"') is not None
    assert compiled.search("result: PASS") is None
