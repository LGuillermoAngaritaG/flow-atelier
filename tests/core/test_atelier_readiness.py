"""Atelier.tool_readiness — preflight runnability probe."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.schemas.conduit import Conduit


@pytest.fixture
def atelier(tmp_path, _isolate_global_atelier_dir):
    """Construct an Atelier rooted under tmp_path with an isolated global dir.

    :param tmp_path: pytest temp directory fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    global_dir: Path = _isolate_global_atelier_dir
    return Atelier(
        base_dir=tmp_path / ".atelier",
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=global_dir,
        ),
    )


def _conduit(tasks: list[dict]) -> Conduit:
    """Build a minimal Conduit from a list of task dicts.

    :param tasks: task payloads (each with name/description/task/tool).
    """
    return Conduit.model_validate(
        {"name": "c", "description": "d", "tasks": tasks}
    )


def test_all_bash_conduit_is_ready(atelier):
    """A conduit using only always-available tools reports no problems."""
    conduit = _conduit(
        [
            {"name": "a", "description": "a", "task": "echo hi", "tool": "tool:bash"},
            {"name": "b", "description": "b", "task": "echo bye", "tool": "tool:bash"},
        ]
    )
    assert atelier.tool_readiness(conduit) == []


def test_unavailable_harness_is_reported(atelier):
    """A task whose harness probe fails surfaces a message naming task+tool."""
    atelier.executors["harness:claude-code"].is_available = lambda: (False, "no npx")
    conduit = _conduit(
        [
            {"name": "build", "description": "b", "task": "do", "tool": "harness:claude-code"},
        ]
    )
    problems = atelier.tool_readiness(conduit)
    assert problems == ["task 'build' [harness:claude-code]: no npx"]


def test_unregistered_tool_is_reported(atelier):
    """Removing an executor key surfaces a 'no executor registered' message."""
    del atelier.executors["harness:codex"]
    conduit = _conduit(
        [
            {"name": "x", "description": "x", "task": "do", "tool": "harness:codex"},
        ]
    )
    problems = atelier.tool_readiness(conduit)
    assert problems == [
        "task 'x': no executor registered for tool 'harness:codex'"
    ]
