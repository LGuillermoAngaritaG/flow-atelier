"""Atelier facade: flow history (list_prior_flows, get_flow_logs)."""
from __future__ import annotations

import pytest

from app.core.atelier import Atelier
from app.schemas.api import PriorFlow, RunTaskInput
from app.schemas.log import LogEntry


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


async def test_list_prior_flows_after_run_returns_one(atelier):
    payload = RunTaskInput(
        name="echo",
        description="d",
        task="echo hi",
        tool="tool:bash",
        inputs={},
        run_path="/tmp",
    )
    out = await atelier.run_single_task(payload)
    flows = atelier.list_prior_flows()
    assert len(flows) == 1
    assert isinstance(flows[0], PriorFlow)
    assert flows[0].flow_id == out.flow_id
    assert flows[0].status == "completed"


async def test_get_flow_logs_round_trips(atelier):
    payload = RunTaskInput(
        name="echo",
        description="d",
        task="echo round-trip",
        tool="tool:bash",
        inputs={},
        run_path="/tmp",
    )
    out = await atelier.run_single_task(payload)
    logs = atelier.get_flow_logs(out.flow_id)
    assert all(isinstance(e, LogEntry) for e in logs)
    assert any("round-trip" in (e.stdout or "") for e in logs)


def test_get_flow_logs_unknown_raises(atelier):
    with pytest.raises(FileNotFoundError):
        atelier.get_flow_logs("not_a_flow")


def test_list_prior_flows_empty(atelier):
    assert atelier.list_prior_flows() == []
