"""`_parse_inputs` CLI helper tests."""
from __future__ import annotations

import pytest
import typer

from flow_atelier.cli._shared import _parse_inputs


def test_parse_inputs_happy_path():
    """Valid key=value pairs parse into a dict."""
    assert _parse_inputs(["a=1", "b=two"]) == {"a": "1", "b": "two"}


def test_parse_inputs_missing_equals_rejected():
    """A pair without ``=`` raises a clear parameter error."""
    with pytest.raises(typer.BadParameter):
        _parse_inputs(["noequals"])


def test_parse_inputs_empty_key_rejected():
    """``=value`` (blank key) is rejected instead of silently kept."""
    with pytest.raises(typer.BadParameter):
        _parse_inputs(["=value"])


def test_parse_inputs_duplicate_key_rejected():
    """A repeated key is rejected instead of silently keeping the last."""
    with pytest.raises(typer.BadParameter):
        _parse_inputs(["x=a", "x=b"])
