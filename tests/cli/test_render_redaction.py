"""Tests for credential masking on the tool-argument render path.

Tool payloads were always persisted, but they are now *rendered*, so a token
in a `curl -H` ends up on screen and in whatever a user pastes into an issue.
The masking is a heuristic, not a guarantee — these tests pin the shapes it
is expected to catch and the shapes it must not mangle.
"""
from __future__ import annotations

import json

from flow_atelier.cli.rendering.render import _redact, _render_step, _tool_arg
from flow_atelier.schemas.log import IntermediateStep, StepKind


def _tool_call(payload: dict) -> IntermediateStep:
    """Build a tool_call step carrying ``payload`` as its JSON input.

    :param payload: raw tool input to serialize onto the step.
    :returns: the constructed :class:`IntermediateStep`.
    """
    return IntermediateStep(
        kind=StepKind.tool_call,
        tool_name="Bash",
        tool_input=json.dumps(payload),
    )


def test_redacts_bearer_token():
    """An Authorization header value is masked, the rest of the command is not."""
    out = _redact('curl -H "Authorization: Bearer sk-abc123def456ghi789" https://x')
    assert "sk-abc123def456ghi789" not in out
    assert "curl" in out and "https://x" in out


def test_redacts_vendor_key_prefixes():
    """Well-known key prefixes are masked wherever they appear."""
    for secret in (
        "sk-ant-api03-AAAAbbbbCCCCdddd",
        "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "xoxb-1234567890-abcdefghij",
        "AKIAIOSFODNN7EXAMPLE",
    ):
        out = _redact(f"deploy --key {secret} --region us-east-1")
        assert secret not in out, secret
        assert "us-east-1" in out


def test_redacts_flag_and_env_style_assignments():
    """`--password X`, `TOKEN=X` and `api_key: X` are all masked."""
    for raw in (
        "mysql --password hunter2 --host db",
        "run GITHUB_TOKEN=ghs_zzzzzzzzzzzzzzzzzzzz build",
        "post --data api_key: abcdef123456",
    ):
        out = _redact(raw)
        assert "hunter2" not in out
        assert "ghs_zzzzzzzzzzzzzzzzzzzz" not in out
        assert "abcdef123456" not in out


def test_leaves_ordinary_commands_alone():
    """A command with no credential shape survives byte for byte."""
    raw = "pytest tests/ -x --maxfail=1 -k 'not slow'"
    assert _redact(raw) == raw


def test_tool_arg_masks_bash_command():
    """The rendered argument for a Bash call carries no token."""
    step = _tool_call({"command": "curl -H 'Authorization: Bearer ghp_" + "A" * 30 + "'"})
    assert "ghp_" not in _tool_arg(step)
    assert "***" in _tool_arg(step)


def test_tool_arg_keeps_plain_file_path():
    """A file path is not credential-shaped and renders unchanged."""
    step = _tool_call({"file_path": "src/app/main.py"})
    assert _tool_arg(step) == "src/app/main.py"


def test_failed_tool_output_is_redacted():
    """A failing tool's output is masked too — it is rendered on the run stream."""
    step = IntermediateStep(
        kind=StepKind.tool_result,
        tool_status="failed",
        tool_output="401 from https://api.example.com with Bearer sk-live-abcdef123456",
    )
    assert "sk-live-abcdef123456" not in _render_step(step).plain
