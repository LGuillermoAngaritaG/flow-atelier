"""/tasks/run REST tests."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.atelier import Atelier
from app.services.api.app import FastApiServer


@pytest.fixture
async def fixture(tmp_path, monkeypatch):
    """Yield an httpx client wired to a fresh Atelier instance.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    app = FastApiServer().create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=15.0
    ) as c:
        yield c, atelier, tmp_path


async def test_run_task_executes_bash_and_returns_logs(fixture):
    """Verify POST /tasks/run executes a bash task and returns logs.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, atelier, tmp_path = fixture
    payload = {
        "name": "echo",
        "description": "ad-hoc",
        "task": "echo task-api-output",
        "tool": "tool:bash",
        "run_path": str(tmp_path),
    }
    resp = await client.post("/tasks/run", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["flow_id"]
    assert body["logs"]
    assert any(
        "task-api-output" in (entry.get("stdout") or "")
        for entry in body["logs"]
    )

    flow_dir = atelier.store._flow_dir(body["flow_id"])
    raw_logs = json.loads((flow_dir / "logs.json").read_text())
    assert raw_logs


async def test_run_task_invalid_payload_returns_400(fixture):
    """Verify an invalid /tasks/run payload returns 400 or 422.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, _ = fixture
    resp = await client.post(
        "/tasks/run", json={"name": "x"}  # missing task, tool, run_path
    )
    assert resp.status_code in (400, 422)
