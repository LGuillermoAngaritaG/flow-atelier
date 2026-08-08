"""CLI tests for ``atelier ask``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from flow_atelier.cli import app

FAKE_AGENT = Path(__file__).resolve().parents[1] / "fixtures" / "fake_acp_agent.py"


def test_ask_runs_an_interactive_claude_session_in_path(tmp_path, monkeypatch) -> None:
    """The query and path reach one interactive Claude task end to end.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    script = json.dumps(
        {
            "turns": [
                {"chunks": ["Which colour? "], "stop": "end_turn"},
                {"chunks": ["Blue it is. [ATELIER_DONE]"], "stop": "end_turn"},
            ]
        }
    )
    monkeypatch.setenv(
        "ATELIER_CLAUDE_LAUNCH_CMD",
        json.dumps([sys.executable, str(FAKE_AGENT), "--script", script]),
    )

    query = "Help me write a specification"
    result = CliRunner().invoke(
        app,
        ["ask", query, "--path", str(project)],
        input="blue\n",
    )

    assert result.exit_code == 0, result.output
    assert "Which colour?" in result.output
    assert "Blue it is." in result.output
    assert "[ATELIER_DONE]" not in result.output

    flow_dirs = list((tmp_path / ".atelier" / "flows").iterdir())
    assert len(flow_dirs) == 1
    progress = json.loads((flow_dirs[0] / "progress.json").read_text())
    assert progress["run_path"] == str(project.resolve())
    logs = [json.loads(line) for line in (flow_dirs[0] / "logs.jsonl").read_text().splitlines()]
    assert logs[-1]["command"] == query
    assert logs[-1]["task"] == "chat"
    assert logs[-1]["tool"] == "harness:claude-code"
    assert "Blue it is." in logs[-1]["output"]


def test_ask_requires_a_path(tmp_path, monkeypatch) -> None:
    """The command refuses to start without an explicit target directory.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["ask", "hello"])
    assert result.exit_code == 2
    assert "--path" in result.output
