"""/tasks/run REST tests."""
from __future__ import annotations

import httpx
import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.services.api.app import FastApiServer


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
        transport=transport, base_url="http://127.0.0.1", timeout=15.0
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

    raw_logs = [e.model_dump() for e in atelier.store.read_logs(body["flow_id"])]
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


async def test_run_task_hyphenated_name_returns_400(fixture):
    """Verify a well-formed body with a hyphenated task name returns 400, not 500.

    ``RunTaskInput`` accepts any string for ``name``, but the conduit schema
    rejects hyphens, so the model_validate happening inside run_single_task must
    surface as a clean 4xx rather than an opaque 500.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, tmp_path = fixture
    payload = {
        "name": "my-task",
        "description": "ad-hoc",
        "task": "echo hi",
        "tool": "tool:bash",
        "run_path": str(tmp_path),
    }
    resp = await client.post("/tasks/run", json=payload)
    assert resp.status_code == 400, resp.text
    assert "invalid task definition" in resp.json()["detail"]


async def test_run_task_unknown_tool_returns_400(fixture):
    """Verify a well-formed body with an unknown ``tool`` returns 400, not 500.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, tmp_path = fixture
    payload = {
        "name": "echo",
        "description": "ad-hoc",
        "task": "echo hi",
        "tool": "tool:nonsense",
        "run_path": str(tmp_path),
    }
    resp = await client.post("/tasks/run", json=payload)
    assert resp.status_code == 400, resp.text
    assert "invalid task definition" in resp.json()["detail"]
