"""Unit tests for the conditions module."""
import pytest

from app.modules.conditions import (
    ConditionalDependency,
    DependencyParseError,
    PlainDependency,
    evaluate,
    parse_dependency,
)
from app.schemas.progress import TaskStatus


def test_parse_plain():
    dep = parse_dependency("clone_repo")
    assert isinstance(dep, PlainDependency)
    assert dep.task == "clone_repo"


def test_parse_match():
    dep = parse_dependency("review.output.match(VERDICT:\\s*APPROVE)")
    assert isinstance(dep, ConditionalDependency)
    assert dep.task == "review"
    assert dep.negate is False
    assert dep.pattern == "VERDICT:\\s*APPROVE"


def test_parse_not_match():
    dep = parse_dependency("review.output.not_match(VERDICT:\\s*APPROVE)")
    assert isinstance(dep, ConditionalDependency)
    assert dep.negate is True


def test_parse_regex_with_inner_parens():
    # final closing paren delimits; inner `)` is part of the regex
    dep = parse_dependency("x.output.match(foo(bar))")
    assert isinstance(dep, ConditionalDependency)
    assert dep.pattern == "foo(bar)"


def test_parse_invalid_regex():
    with pytest.raises(DependencyParseError):
        parse_dependency("x.output.match([unclosed)")


def test_parse_missing_close_paren():
    with pytest.raises(DependencyParseError):
        parse_dependency("x.output.match(foo")


def test_parse_empty():
    with pytest.raises(DependencyParseError):
        parse_dependency("")


def test_evaluate_plain_completed():
    dep = parse_dependency("a")
    status = {"a": TaskStatus.completed}
    assert evaluate(dep, status, {"a": "ok"}) == ("satisfied", None)


def test_evaluate_plain_running():
    dep = parse_dependency("a")
    assert evaluate(dep, {"a": TaskStatus.running}, {}) == ("wait", None)


def test_evaluate_plain_failed():
    dep = parse_dependency("a")
    result, reason = evaluate(dep, {"a": TaskStatus.failed}, {})
    assert result == "skip"
    assert "failed" in reason


def test_evaluate_plain_skipped():
    dep = parse_dependency("a")
    result, reason = evaluate(dep, {"a": TaskStatus.skipped}, {})
    assert result == "skip"
    assert "skipped" in reason


def test_evaluate_conditional_match_satisfied():
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    assert evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "blah\nVERDICT: APPROVE\n"},
    ) == ("satisfied", None)


def test_evaluate_conditional_match_not_met_skips():
    dep = parse_dependency("a.output.match(VERDICT:\\s*APPROVE)")
    result, reason = evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "VERDICT: REJECT"},
    )
    assert result == "skip"
    assert "condition not met" in reason


def test_evaluate_not_match_satisfied():
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    assert evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "all good"},
    ) == ("satisfied", None)


def test_evaluate_not_match_triggers_skip():
    dep = parse_dependency("a.output.not_match(CRITICAL)")
    result, _ = evaluate(
        dep,
        {"a": TaskStatus.completed},
        {"a": "CRITICAL vuln"},
    )
    assert result == "skip"


def test_evaluate_unknown_task_skips():
    dep = parse_dependency("ghost")
    result, reason = evaluate(dep, {"a": TaskStatus.completed}, {})
    assert result == "skip"
    assert "unknown" in reason


# ---------------------------------------------------------------- output predicate


def test_parse_output_predicate_match():
    from app.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.match(DONE)")
    assert pattern.search("foo DONE bar")
    assert not pattern.search("nope")
    assert negate is False


def test_parse_output_predicate_not_match():
    from app.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.not_match(RETRY)")
    assert pattern.search("RETRY now")
    assert negate is True


def test_parse_output_predicate_inner_parens():
    from app.modules.conditions import parse_output_predicate

    pattern, negate = parse_output_predicate("output.match(foo(bar))")
    assert pattern.pattern == "foo(bar)"
    assert negate is False


def test_parse_output_predicate_bare_regex_rejected():
    from app.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("DONE")


def test_parse_output_predicate_invalid_regex_rejected():
    from app.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("output.match([unclosed)")


def test_parse_output_predicate_missing_close_paren():
    from app.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("output.match(foo")


def test_parse_output_predicate_empty_rejected():
    from app.modules.conditions import parse_output_predicate

    with pytest.raises(DependencyParseError):
        parse_output_predicate("")
