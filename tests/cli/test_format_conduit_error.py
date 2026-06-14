"""Unit tests for the conduit-error formatting helper."""
import pytest
import yaml
from pydantic import ValidationError

from flow_atelier.cli.rendering.render import format_conduit_error
from flow_atelier.schemas.conduit import TaskDefinition


def test_validation_error_is_one_line_with_field_path():
    """A pydantic ValidationError renders as a single line naming the field."""
    with pytest.raises(ValidationError) as ei:
        TaskDefinition.model_validate(
            {"name": "t", "description": "d", "task": "echo", "tool": "tool:nope"}
        )
    msg = format_conduit_error(ei.value)
    assert "\n" not in msg
    assert "tool" in msg


def test_yaml_error_is_one_line_with_line_number():
    """A yaml.YAMLError with a mark renders one line including the line number."""
    try:
        yaml.safe_load("a: [1, 2\nb: 3\n")
    except yaml.YAMLError as e:
        msg = format_conduit_error(e)
    assert "\n" not in msg
    assert "line" in msg


def test_value_error_is_passed_through_one_line():
    """A plain ValueError (e.g. name/folder mismatch) is surfaced verbatim."""
    msg = format_conduit_error(
        ValueError("conduit.yaml name 'a' != folder name 'b'")
    )
    assert msg == "conduit.yaml name 'a' != folder name 'b'"


def test_value_error_collapses_newlines():
    """Multi-line error text collapses to a single line."""
    msg = format_conduit_error(ValueError("line one\nline two"))
    assert msg == "line one line two"
