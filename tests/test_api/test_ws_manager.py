"""WebSocketBroker unit tests."""
from __future__ import annotations

import asyncio

import pytest

from app.services.api.ws_manager import WebSocketBroker


class _Sink:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.fixture
def broker() -> WebSocketBroker:
    return WebSocketBroker(send=_Sink())


async def test_send_passes_envelope_to_sink(broker):
    sink: _Sink = broker.send_callable  # type: ignore[assignment]
    await broker.send({"type": "started", "flow_id": "T-1"})
    assert sink.sent == [{"type": "started", "flow_id": "T-1"}]


async def test_register_and_deliver_hitl_answer(broker):
    broker.register_flow("T-1")
    await broker.deliver_hitl_answer("T-1", {"q": "y"})
    answer = await broker.await_hitl_answer("T-1")
    assert answer == {"q": "y"}


async def test_await_hitl_answer_is_per_flow(broker):
    broker.register_flow("T-1")
    broker.register_flow("T-2")
    await broker.deliver_hitl_answer("T-2", {"a": 1})
    a = await broker.await_hitl_answer("T-2")
    assert a == {"a": 1}


async def test_track_run_and_cancel(broker):
    fired: dict[str, bool] = {"cancelled": False}

    async def long_running() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            fired["cancelled"] = True
            raise

    task = asyncio.create_task(long_running())
    broker.register_flow("T-1")
    broker.track_run("T-1", task)
    # Yield once so long_running() can hit its sleep before we cancel.
    await asyncio.sleep(0)
    broker.cancel("T-1")
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fired["cancelled"] is True


async def test_cancel_unknown_flow_is_noop(broker):
    broker.cancel("T-ghost")  # must not raise


async def test_deliver_to_unregistered_flow_raises(broker):
    with pytest.raises(KeyError):
        await broker.deliver_hitl_answer("T-x", {"q": "y"})
