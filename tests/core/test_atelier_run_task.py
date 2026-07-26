"""Atelier facade: run_single_task (ad-hoc one-task conduit)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.schemas.api import RunTaskInput, RunTaskOutput

FAKE_AGENT = Path(__file__).resolve().parents[1] / "fixtures" / "fake_acp_agent.py"


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    """Construct an Atelier instance rooted under tmp_path.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


async def test_run_single_task_runs_bash_echo_and_returns_logs(atelier, tmp_path):
    """Verify run_single_task runs bash echo and returns logs with exit 0.

    :param atelier: Atelier facade fixture.
    """
    payload = RunTaskInput(
        name="echo",
        description="ad-hoc echo",
        task="echo hello-from-task",
        tool="tool:bash",
        run_path=str(tmp_path),
    )
    out = await atelier.run_single_task(payload)
    assert isinstance(out, RunTaskOutput)
    assert out.flow_id
    assert out.logs
    assert any("hello-from-task" in (e.stdout or "") for e in out.logs)
    assert out.logs[-1].exit_code == 0


async def test_run_single_task_persists_flow_dir(atelier, tmp_path):
    """Verify run_single_task writes the flow's logs.jsonl to disk.

    :param atelier: Atelier facade fixture.
    """
    payload = RunTaskInput(
        name="echo",
        description="ad-hoc echo",
        task="echo persisted",
        tool="tool:bash",
        run_path=str(tmp_path),
    )
    out = await atelier.run_single_task(payload)
    flow_dir = atelier.store._flow_dir(out.flow_id)
    assert (flow_dir / "logs.jsonl").exists()


async def test_run_single_task_drives_a_settings_declared_harness(
    tmp_path, monkeypatch, _isolate_global_atelier_dir
):
    """An ACP agent known only to ATELIER_HARNESSES runs end to end.

    Covers the whole chain the bundled harnesses get for free: settings ->
    executor registry -> task schema -> engine dispatch -> ACP session.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    script = json.dumps({"turns": [{"chunks": ["custom agent ok"], "stop": "end_turn"}]})
    at = Atelier(
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=_isolate_global_atelier_dir,
            harnesses={"fake": [sys.executable, str(FAKE_AGENT), "--script", script]},
        ),
    )
    out = await at.run_single_task(
        RunTaskInput(
            name="ask",
            description="ad-hoc harness task",
            task="hello",
            tool="harness:fake",
            run_path=str(tmp_path),
        )
    )
    assert out.logs[-1].exit_code == 0
    assert "custom agent ok" in (out.logs[-1].stdout or "")


async def test_run_single_task_failure_returns_non_zero_exit(atelier, tmp_path):
    """Verify run_single_task returns a non-zero exit code on failure.

    :param atelier: Atelier facade fixture.
    """
    payload = RunTaskInput(
        name="boom",
        description="explode",
        task="exit 7",
        tool="tool:bash",
        run_path=str(tmp_path),
    )
    out = await atelier.run_single_task(payload)
    assert out.flow_id
    assert out.logs
    assert out.logs[-1].exit_code != 0
