"""/ws/run-conduit subscribes connections to the scheduler bus when attached."""
from __future__ import annotations

import asyncio
import json

import pytest
from starlette.testclient import TestClient

from flow_atelier.core.atelier import Atelier
from flow_atelier.services.api.app import FastApiServer
from flow_atelier.services.api.scheduler_bus import SchedulerEventBus


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Build an Atelier with a scheduler bus attached and a FastAPI app.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    bus = SchedulerEventBus()
    atelier.scheduler_bus = bus  # type: ignore[attr-defined]
    app = FastApiServer().create_app(atelier)
    return atelier, app, bus


def test_ws_subscribes_to_scheduler_bus_when_attached(env):
    """A connected WS must receive bus broadcasts; disconnect unsubscribes.

    :param env: atelier+app+bus fixture.
    """
    atelier, app, bus = env
    with TestClient(app, base_url="http://127.0.0.1", headers={"host": "127.0.0.1"}) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            # Broadcast a fake scheduled-run envelope through the bus.
            asyncio.run(
                bus.broadcast({"type": "scheduled_run_started", "flow_id": "F1"})
            )
            envelope = json.loads(ws.receive_text())
            assert envelope == {"type": "scheduled_run_started", "flow_id": "F1"}
        # Socket closed → subscriber removed.
        assert bus._subscribers == set()


async def test_broadcast_drops_slow_subscriber_within_timeout():
    """A subscriber slower than send_timeout is dropped, not waited on.

    Bounds head-of-line blocking on the scheduler fire path.
    """
    bus = SchedulerEventBus(send_timeout=0.02)
    fast_seen: list[dict] = []

    async def fast(envelope: dict) -> None:
        """Record the envelope immediately."""
        fast_seen.append(envelope)

    async def slow(envelope: dict) -> None:
        """Block far longer than the bus timeout."""
        await asyncio.sleep(5)

    bus.subscribe(fast)
    bus.subscribe(slow)
    start = asyncio.get_running_loop().time()
    await bus.broadcast({"type": "x"})
    elapsed = asyncio.get_running_loop().time() - start

    assert elapsed < 1.0  # did not wait the full 5s on the slow socket
    assert fast_seen == [{"type": "x"}]
    assert slow not in bus._subscribers  # dropped after timeout
    assert fast in bus._subscribers


def test_ws_with_no_bus_attached_still_connects(tmp_path, monkeypatch):
    """When no bus is attached the WS continues to work for run/HITL only.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    app = FastApiServer().create_app(atelier)
    with TestClient(app, base_url="http://127.0.0.1", headers={"host": "127.0.0.1"}) as client:
        with client.websocket_connect("/ws/run-conduit"):
            pass
