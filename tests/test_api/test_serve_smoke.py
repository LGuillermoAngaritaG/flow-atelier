"""End-to-end smoke test for ``atelier serve``."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.services.api.app import FastApiServer
from flow_atelier.services.scheduler import SchedulerDaemon, default_local_zone


@pytest.mark.timeout(15)
async def test_serve_smoke_boots_and_serves_conduits(tmp_path, monkeypatch):
    """Boot uvicorn programmatically on an ephemeral port, hit GET /conduits,
    then shut down cleanly.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    monkeypatch.delenv("ATELIER_ATELIER_DIR", raising=False)
    atelier = Atelier(
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=tmp_path / ".atelier-global",
        ),
    )
    daemon = SchedulerDaemon(
        atelier.schedule_store,
        default_zone=default_local_zone(),
        default_working_dir=tmp_path,
        reload_interval_seconds=3600,
    )
    atelier.scheduler_daemon = daemon  # type: ignore[attr-defined]

    @asynccontextmanager
    async def _lifespan(_app):
        """Start/stop the scheduler daemon around the app lifespan.

        :param _app: FastAPI app instance (unused).
        """
        await daemon.start()
        try:
            yield
        finally:
            await daemon.stop()

    app = FastApiServer().create_app(atelier)
    app.router.lifespan_context = _lifespan

    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())

    # Wait until uvicorn binds.
    deadline = asyncio.get_event_loop().time() + 5.0
    while not server.started and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)
    assert server.started, "uvicorn did not start"

    port = server.servers[0].sockets[0].getsockname()[1]
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as c:
        resp = await c.get("/conduits", timeout=5.0)
    assert resp.status_code == 200
    assert resp.json() == []

    server.should_exit = True
    await serve_task
