"""Templating unit tests."""
import pytest

from app.modules.templating import SkipSignal, TemplateError, resolve


def test_resolve_inputs():
    """Verify resolve() substitutes a single input placeholder."""
    out = resolve("hello {{inputs.name}}!", {"name": "world"}, {})
    assert out == "hello world!"


def test_resolve_multiple():
    """Verify resolve() substitutes multiple input placeholders."""
    out = resolve(
        "{{inputs.a}}-{{inputs.b}}-{{inputs.a}}",
        {"a": "x", "b": "y"},
        {},
    )
    assert out == "x-y-x"


def test_resolve_missing_input_raises():
    """Verify resolve() raises TemplateError on missing input."""
    with pytest.raises(TemplateError):
        resolve("{{inputs.missing}}", {}, {})


def test_resolve_task_output():
    """Verify resolve() substitutes a task output reference."""
    out = resolve("v={{get_version.output}}", {}, {"get_version": "1.2.3"})
    assert out == "v=1.2.3"


def test_resolve_mixed():
    """Verify resolve() handles mixed input and task-output references."""
    out = resolve(
        "echo '{{inputs.env}}: {{build.output}}'",
        {"env": "prod"},
        {"build": "ok"},
    )
    assert out == "echo 'prod: ok'"


def test_resolve_task_unavailable_raises_skip():
    """Verify resolve() raises SkipSignal for unavailable tasks."""
    with pytest.raises(SkipSignal):
        resolve("{{a.output}}", {}, {}, unavailable_tasks={"a"})


def test_resolve_task_not_yet_completed_raises_skip():
    """Verify resolve() raises SkipSignal when task output is absent."""
    with pytest.raises(SkipSignal):
        resolve("{{a.output}}", {}, {})


def test_resolve_unknown_expression():
    """Verify resolve() raises TemplateError on unknown expression."""
    with pytest.raises(TemplateError):
        resolve("{{weird}}", {}, {})


def test_resolve_non_template_string_unchanged():
    """Verify resolve() returns plain strings unchanged."""
    assert resolve("plain text", {}, {}) == "plain text"
