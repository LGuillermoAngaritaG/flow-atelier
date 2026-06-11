"""/schedules REST tests."""
from __future__ import annotations

import httpx
import pytest
import yaml

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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, atelier, tmp_path


def _payload(**overrides):
    """Build a baseline schedule payload, with optional overrides.

    :param overrides: keys to override on the baseline payload.
    """
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
    """Verify GET /schedules starts empty.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, _ = fixture
    resp = await client.get("/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_schedule_returns_201(fixture):
    """Verify POST /schedules returns 201 and a SCH- prefixed id.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, _ = fixture
    resp = await client.post("/schedules", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("SCH-")
    assert body["conduit_name"] == "report"


async def test_create_schedule_persists_to_yaml_file(fixture):
    """Verify a created schedule is persisted to a YAML file under schedules/.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, tmp_path = fixture
    resp = await client.post("/schedules", json=_payload())
    sch_id = resp.json()["id"]
    yaml_path = tmp_path / ".atelier" / "schedules" / "weekday-mornings.yaml"
    raw = yaml.safe_load(yaml_path.read_text())
    assert raw["id"] == sch_id
    assert raw["schedule"]["mode"] == "recurring"
    assert raw["schedule"]["name"] == "weekday mornings"


async def test_create_schedule_invalid_returns_400(fixture):
    """Verify an invalid schedule payload returns 400 or 422.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
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


async def test_delete_schedule_removes_from_list(fixture):
    """Verify DELETE /schedules/<id> removes it from disk and from the list.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, _ = fixture
    resp = await client.post("/schedules", json=_payload())
    sch_id = resp.json()["id"]

    resp = await client.delete(f"/schedules/{sch_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sch_id

    listed = await client.get("/schedules")
    assert listed.json() == []


async def test_delete_unknown_returns_404(fixture):
    """Verify deleting an unknown schedule returns 404.

    :param fixture: client+atelier+tmp_path tuple fixture.
    """
    client, _, _ = fixture
    resp = await client.delete("/schedules/SCH-nope")
    assert resp.status_code == 404


async def test_create_logs_when_daemon_sync_fails(fixture, caplog):
    """Verify a failing daemon.sync() during create is logged, not swallowed.

    :param fixture: client+atelier+tmp_path tuple fixture.
    :param caplog: pytest log capture fixture.
    """
    import logging

    client, atelier, _ = fixture

    class _BoomDaemon:
        async def sync(self) -> None:
            raise RuntimeError("boom")

    atelier.scheduler_daemon = _BoomDaemon()
    with caplog.at_level(logging.WARNING, logger="flow_atelier.routes.schedules"):
        resp = await client.post("/schedules", json=_payload())
    assert resp.status_code == 201
    assert any("scheduler sync after create failed" in r.message for r in caplog.records)
