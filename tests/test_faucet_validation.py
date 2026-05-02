"""Validation tests for `Conduit.faucet`.

A faucet conduit is fed by an external channel (Telegram, Discord, ...). The
channel injects implicit inputs (`_message`, `_channel`, `_session_key`) at
runtime, so a faucet conduit must NOT declare its own `inputs:` block, and it
must contain at least one `harness:*` task — that is the conversational ACP
turn the channel message drives.
"""
from __future__ import annotations

import pytest

from app.schemas.conduit import Conduit


def _bash_task(name: str = "do") -> dict:
    return {
        name: {
            "description": "d",
            "task": "echo hi",
            "tool": "tool:bash",
            "depends_on": [],
        }
    }


def _harness_task(name: str = "chat") -> dict:
    return {
        name: {
            "description": "d",
            "task": "respond to {{_message}}",
            "tool": "harness:claude-code",
            "depends_on": [],
        }
    }


def test_faucet_default_is_false():
    """Existing conduits with no `faucet` field default to non-faucet mode."""
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "tasks": [_bash_task()],
        }
    )
    assert c.faucet is False


def test_faucet_true_with_inputs_rejected():
    """`faucet=True` + `inputs:` is incoherent — channel supplies inputs."""
    with pytest.raises(Exception, match="faucet conduits cannot declare inputs"):
        Conduit.model_validate(
            {
                "name": "x",
                "description": "d",
                "faucet": True,
                "inputs": {"foo": "bar"},
                "tasks": [_harness_task()],
            }
        )


def test_faucet_true_without_harness_task_rejected():
    """A faucet conduit must contain ≥1 `harness:*` task — that's the ACP turn."""
    with pytest.raises(Exception, match="at least one harness:.* task"):
        Conduit.model_validate(
            {
                "name": "x",
                "description": "d",
                "faucet": True,
                "tasks": [_bash_task("a"), _bash_task("b")],
            }
        )


def test_faucet_true_with_harness_task_ok():
    """Happy path: `faucet=True`, no `inputs:`, ≥1 harness task."""
    c = Conduit.model_validate(
        {
            "name": "echo",
            "description": "d",
            "faucet": True,
            "tasks": [_harness_task()],
        }
    )
    assert c.faucet is True
    assert c.inputs == {}


def test_faucet_true_with_harness_and_bash_tasks_ok():
    """Mixed harness + bash tasks are fine as long as ≥1 is harness."""
    c = Conduit.model_validate(
        {
            "name": "echo",
            "description": "d",
            "faucet": True,
            "tasks": [_bash_task("setup"), _harness_task("chat")],
        }
    )
    assert c.faucet is True


def test_faucet_false_with_inputs_unchanged():
    """Non-faucet conduits keep all existing behavior — `inputs:` is fine."""
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "faucet": False,
            "inputs": {"foo": "a foo"},
            "tasks": [_bash_task()],
        }
    )
    assert c.faucet is False
    assert c.inputs == {"foo": "a foo"}


def test_faucet_false_without_harness_task_unchanged():
    """Non-faucet conduits don't need a harness task — still allowed."""
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "tasks": [_bash_task("a"), _bash_task("b")],
        }
    )
    assert c.faucet is False
