"""/conduits CRUD round-trip tests."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.services.api.app import FastApiServer


@pytest.fixture
async def client(tmp_path, _isolate_global_atelier_dir):
    """Yield an httpx client wired to a fresh Atelier instance.

    :param tmp_path: pytest temp directory fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    global_dir: Path = _isolate_global_atelier_dir
    atelier = Atelier(
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=global_dir,
        ),
    )
    app = FastApiServer().create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _payload(name: str = "release_notes", description: str = "Generate notes"):
    """Build a baseline conduit payload.

    :param name: conduit name to embed in the payload.
    :param description: conduit description to embed in the payload.
    """
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
    """Verify GET /conduits returns an empty array initially.

    :param client: httpx client fixture.
    """
    resp = await client.get("/conduits")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_unknown_conduit_returns_404(client):
    """Verify GET /conduits/<unknown> returns 404 with an error body.

    :param client: httpx client fixture.
    """
    resp = await client.get("/conduits/ghost")
    assert resp.status_code == 404
    assert "detail" in resp.json()


# ---------------------------------------------------------------- create


async def test_create_conduit_returns_201_and_persists(client):
    """Verify POST /conduits returns 201 and the conduit is listed afterwards.

    :param client: httpx client fixture.
    """
    resp = await client.post("/conduits", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "release_notes"

    listed = await client.get("/conduits")
    items = listed.json()
    assert any(item["name"] == "release_notes" for item in items)


async def test_create_conduit_collision_returns_409(client):
    """Verify creating a conduit with a duplicate name returns 409.

    :param client: httpx client fixture.
    """
    await client.post("/conduits", json=_payload())
    resp = await client.post("/conduits", json=_payload())
    assert resp.status_code == 409


async def test_create_conduit_invalid_returns_400(client):
    """Verify an invalid conduit payload returns 400 or 422.

    :param client: httpx client fixture.
    """
    bad = {"name": "x", "description": "d"}  # missing tasks
    resp = await client.post("/conduits", json=bad)
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------- update


async def test_update_conduit_partial_returns_200(client):
    """Verify PATCH /conduits/<name> applies partial updates.

    :param client: httpx client fixture.
    """
    await client.post("/conduits", json=_payload(description="old"))
    resp = await client.patch(
        "/conduits/release_notes", json={"description": "new"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "new"


async def test_update_unknown_returns_404(client):
    """Verify patching an unknown conduit returns 404.

    :param client: httpx client fixture.
    """
    resp = await client.patch(
        "/conduits/ghost", json={"description": "anything"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------- delete


async def test_delete_conduit_returns_204(client):
    """Verify DELETE /conduits/<name> returns 204 and removes the conduit.

    :param client: httpx client fixture.
    """
    await client.post("/conduits", json=_payload())
    resp = await client.delete("/conduits/release_notes")
    assert resp.status_code == 204
    listed = await client.get("/conduits")
    assert listed.json() == []


async def test_delete_unknown_returns_404(client):
    """Verify deleting an unknown conduit returns 404.

    :param client: httpx client fixture.
    """
    resp = await client.delete("/conduits/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------- open-path


async def test_open_path_invokes_opener(client, monkeypatch):
    """Verify POST /conduits/open-path invokes the subprocess opener.

    :param client: httpx client fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    await client.post("/conduits", json=_payload())
    calls = []

    class _FakeProc:
        def poll(self):
            """Return ``None`` to indicate the fake process is still running."""
            return None

    def fake_popen(cmd, *a, **kw):
        """Capture the command and return a fake process handle.

        :param cmd: subprocess command argv passed to Popen.
        :param a: positional args forwarded by callers (ignored).
        :param kw: keyword args forwarded by callers (ignored).
        """
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
