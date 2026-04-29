"""/conduits CRUD round-trip tests."""
from __future__ import annotations

import httpx
import pytest

from app.core.atelier import Atelier
from app.services.api.app import FastApiServer


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    app = FastApiServer().create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _payload(name: str = "release_notes", description: str = "Generate notes"):
    return {
        "name": name,
        "description": description,
        "tasks": [
            {
                "name": "echo",
                "description": "echo",
                "task": "echo hi",
                "tool": "tool:bash",
                "depends_on": [],
            }
        ],
    }


# ---------------------------------------------------------------- read


async def test_list_conduits_returns_empty_array(client):
    resp = await client.get("/conduits")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_unknown_conduit_returns_404(client):
    resp = await client.get("/conduits/ghost")
    assert resp.status_code == 404
    assert "error" in resp.json()


# ---------------------------------------------------------------- create


async def test_create_conduit_returns_201_and_persists(client):
    resp = await client.post("/conduits", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "release_notes"

    listed = await client.get("/conduits")
    items = listed.json()
    assert any(item["name"] == "release_notes" for item in items)


async def test_create_conduit_collision_returns_409(client):
    await client.post("/conduits", json=_payload())
    resp = await client.post("/conduits", json=_payload())
    assert resp.status_code == 409


async def test_create_conduit_invalid_returns_400(client):
    bad = {"name": "x", "description": "d"}  # missing tasks
    resp = await client.post("/conduits", json=bad)
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------- update


async def test_update_conduit_partial_returns_200(client):
    await client.post("/conduits", json=_payload(description="old"))
    resp = await client.patch(
        "/conduits/release_notes", json={"description": "new"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "new"


async def test_update_unknown_returns_404(client):
    resp = await client.patch(
        "/conduits/ghost", json={"description": "anything"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------- delete


async def test_delete_conduit_returns_204(client):
    await client.post("/conduits", json=_payload())
    resp = await client.delete("/conduits/release_notes")
    assert resp.status_code == 204
    listed = await client.get("/conduits")
    assert listed.json() == []


async def test_delete_unknown_returns_404(client):
    resp = await client.delete("/conduits/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------- open-path


async def test_open_path_invokes_opener(client, monkeypatch):
    await client.post("/conduits", json=_payload())
    calls = []

    class _FakeProc:
        def poll(self):
            return None

    def fake_popen(cmd, *a, **kw):
        calls.append(cmd)
        return _FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    resp = await client.post(
        "/conduits/open-path",
        json={"conduit_name": "release_notes", "run_path": "/tmp"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"opened": True}
    assert calls
