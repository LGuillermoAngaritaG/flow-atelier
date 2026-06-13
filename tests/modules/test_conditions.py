"""Unit tests for the conditions module."""
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


def test_evaluate_plain_completed():
    """Verify evaluate() returns satisfied for a completed plain dep."""
    dep = parse_dependency("a")
    status = {"a": TaskStatus.completed}
    assert evaluate(dep, status, {"a": "ok"}) == ("satisfied", None)


def test_evaluate_plain_running():
    """Verify evaluate() returns wait for a running plain dep."""
    dep = parse_dependency("a")
    assert evaluate(dep, {"a": TaskStatus.running}, {}) == ("wait", None)


def test_evaluate_plain_failed():
    """Verify evaluate() returns skip with a 'failed' reason for failed dep."""
    dep = parse_dependency("a")
    result, reason = evaluate(dep, {"a": TaskStatus.failed}, {})
    assert result == "skip"
    assert "failed" in reason


def test_evaluate_plain_skipped():
    """Verify evaluate() returns skip with a 'skipped' reason for skipped dep."""
    dep = parse_dependency("a")
    result, reason = evaluate(dep, {"a": TaskStatus.skipped}, {})
    assert result == "skip"
    assert "skipped" in reason


def test_evaluate_conditional_match_satisfied():
    """Verify evaluate() returns satisfied when the match pattern hits."""
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    assert evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "blah\nVERDICT: APPROVE\n"},
    ) == ("satisfied", None)


def test_evaluate_conditional_match_not_met_skips():
    """Verify evaluate() skips when the match pattern is absent."""
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    result, reason = evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "VERDICT: REJECT"},
    )
    assert result == "skip"
    assert "condition not met" in reason


def test_evaluate_not_match_satisfied():
    """Verify evaluate() returns satisfied when the not_match pattern is absent."""
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    assert evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "all good"},
    ) == ("satisfied", None)


def test_evaluate_not_match_triggers_skip():
    """Verify evaluate() skips when not_match pattern is present."""
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    result, _ = evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "CRITICAL vuln"},
    )
    assert result == "skip"


def test_evaluate_unknown_task_skips():
    """Verify evaluate() skips when the dependency target is unknown."""
    dep = parse_dependency("ghost")
    result, reason = evaluate(dep, {"a": TaskStatus.completed}, {})
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
def test_evaluate_loop_predicate_until(expr, outputs, expected):
    """Verify evaluate_loop_predicate() in until mode for parametrized cases.

    :param expr: predicate expression under test.
    :param outputs: list of task outputs to evaluate against.
    :param expected: expected boolean result.
    """
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert evaluate_loop_predicate(_pred(expr), outputs, "until") is expected


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
def test_evaluate_loop_predicate_while(expr, outputs, expected):
    """Verify evaluate_loop_predicate() in while mode for parametrized cases.

    :param expr: predicate expression under test.
    :param outputs: list of task outputs to evaluate against.
    :param expected: expected boolean result.
    """
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert evaluate_loop_predicate(_pred(expr), outputs, "while") is expected


def test_evaluate_loop_predicate_empty_outputs_does_not_break():
    """Verify evaluate_loop_predicate() returns False on empty outputs."""
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    assert evaluate_loop_predicate(_pred("output.match(x)"), [], "until") is False
    assert evaluate_loop_predicate(_pred("output.match(x)"), [], "while") is False
    assert evaluate_loop_predicate(_pred("output.not_match(x)"), [], "until") is False
    assert evaluate_loop_predicate(_pred("output.not_match(x)"), [], "while") is False


def test_evaluate_loop_predicate_invalid_mode_raises():
    """Verify evaluate_loop_predicate() raises on an unknown mode."""
    from flow_atelier.modules.conditions import evaluate_loop_predicate

    with pytest.raises(ValueError):
        evaluate_loop_predicate(_pred("output.match(x)"), ["x"], "forever")  # type: ignore[arg-type]


def test_evaluate_loop_predicate_truncates_oversized_output():
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
        evaluate_loop_predicate(_pred("output.match(DONE)"), [beyond_cap], "until")
        is False
    )
    within_cap = "DONE" + "a" * 10
    assert (
        evaluate_loop_predicate(_pred("output.match(DONE)"), [within_cap], "until")
        is True
    )


def test_evaluate_conditional_dep_truncates_oversized_output():
    """Verify evaluate() bounds the candidate output before matching."""
    from flow_atelier.modules.conditions import MATCH_INPUT_CHAR_CAP

    dep = parse_dependency("a.output.match(DONE)")
    statuses = {"a": TaskStatus.completed}
    beyond_cap = "a" * MATCH_INPUT_CHAR_CAP + "DONE"
    result, _ = evaluate(dep, statuses, {"a": beyond_cap})
    assert result == "skip"


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
