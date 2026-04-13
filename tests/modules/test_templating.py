"""Templating unit tests."""
import pytest

from app.modules.templating import SkipSignal, TemplateError, resolve


def test_resolve_inputs():
    out = resolve("hello {{inputs.name}}!", {"name": "world"}, {})
    assert out == "hello world!"


def test_resolve_multiple():
    out = resolve(
        "{{inputs.a}}-{{inputs.b}}-{{inputs.a}}",
        {"a": "x", "b": "y"},
        {},
    )
    assert out == "x-y-x"


def test_resolve_missing_input_raises():
    with pytest.raises(TemplateError):
        resolve("{{inputs.missing}}", {}, {})


def test_resolve_task_output():
    out = resolve("v={{get_version.output}}", {}, {"get_version": "1.2.3"})
    assert out == "v=1.2.3"


def test_resolve_mixed():
    out = resolve(
        "echo '{{inputs.env}}: {{build.output}}'",
        {"env": "prod"},
        {"build": "ok"},
    )
    assert out == "echo 'prod: ok'"


def test_resolve_task_unavailable_raises_skip():
    with pytest.raises(SkipSignal):
        resolve("{{a.output}}", {}, {}, unavailable_tasks={"a"})


def test_resolve_task_not_yet_completed_raises_skip():
    with pytest.raises(SkipSignal):
        resolve("{{a.output}}", {}, {})


def test_resolve_unknown_expression():
    with pytest.raises(TemplateError):
        resolve("{{weird}}", {}, {})


def test_resolve_non_template_string_unchanged():
    assert resolve("plain text", {}, {}) == "plain text"
