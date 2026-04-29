"""/schedules REST tests."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.core.atelier import Atelier
from app.services.api.app import FastApiServer


@pytest.fixture
async def fixture(tmp_path, monkeypatch):
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    app = FastApiServer().create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, atelier, tmp_path


def _payload(**overrides):
    base = {
        "conduit_name": "report",
        "inputs": {"foo": "bar"},
        "run_path": "/tmp/x",
        "schedule": {
            "mode": "recurring",
            "name": "weekday mornings",
            "days": [1, 2, 3, 4, 5],
            "times": ["06:00"],
        },
    }
    base.update(overrides)
    return base


async def test_list_schedules_starts_empty(fixture):
    client, _, _ = fixture
    resp = await client.get("/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_schedule_returns_201(fixture):
    client, _, _ = fixture
    resp = await client.post("/schedules", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("SCH-")
    assert body["conduit_name"] == "report"


async def test_create_schedule_persists_to_json_file(fixture):
    client, _, tmp_path = fixture
    resp = await client.post("/schedules", json=_payload())
    sch_id = resp.json()["id"]
    raw = json.loads((tmp_path / ".atelier" / "schedules.json").read_text())
    assert raw["schedules"][0]["id"] == sch_id
    assert raw["schedules"][0]["schedule"]["mode"] == "recurring"


async def test_create_schedule_invalid_returns_400(fixture):
    client, _, _ = fixture
    resp = await client.post(
        "/schedules",
        json={
            "conduit_name": "x",
            "run_path": "/tmp",
            "schedule": {"mode": "weekly"},
        },
    )
    assert resp.status_code in (400, 422)


async def test_delete_schedule_marks_deleted(fixture):
    client, _, _ = fixture
    resp = await client.post("/schedules", json=_payload())
    sch_id = resp.json()["id"]

    resp = await client.delete(f"/schedules/{sch_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    listed = await client.get("/schedules")
    assert listed.json() == []


async def test_delete_unknown_returns_404(fixture):
    client, _, _ = fixture
    resp = await client.delete("/schedules/SCH-nope")
    assert resp.status_code == 404
