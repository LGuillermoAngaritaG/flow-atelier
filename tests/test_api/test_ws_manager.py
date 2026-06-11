"""WebSocketBroker unit tests."""
from __future__ import annotations

import asyncio

import pytest

from flow_atelier.services.api.ws_manager import WebSocketBroker


class _Sink:
    def __init__(self) -> None:
        """Initialize the sink with an empty list of captured payloads."""
        self.sent: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        """Record an outbound websocket payload.

        :param payload: envelope dict to capture.
        """
        self.sent.append(payload)


@pytest.fixture
def broker() -> WebSocketBroker:
    """Provide a WebSocketBroker backed by a recording sink."""
    return WebSocketBroker(send=_Sink())


async def test_send_passes_envelope_to_sink(broker):
    """Verify broker.send forwards the envelope to the sink.

    :param broker: broker fixture.
    """
    sink: _Sink = broker.send_callable  # type: ignore[assignment]
    await broker.send({"type": "started", "flow_id": "T-1"})
    assert sink.sent == [{"type": "started", "flow_id": "T-1"}]


async def test_register_and_deliver_hitl_answer(broker):
    """Verify a registered flow can receive and await a hitl answer.

    :param broker: broker fixture.
    """
    broker.register_flow("T-1")
    await broker.deliver_hitl_answer("T-1", {"q": "y"})
    answer = await broker.await_hitl_answer("T-1")
    assert answer == {"q": "y"}


async def test_await_hitl_answer_is_per_flow(broker):
    """Verify hitl answers are scoped per flow id.

    :param broker: broker fixture.
    """
    broker.register_flow("T-1")
    broker.register_flow("T-2")
    await broker.deliver_hitl_answer("T-2", {"a": 1})
    a = await broker.await_hitl_answer("T-2")
    assert a == {"a": 1}


async def test_track_run_and_cancel(broker):
    """Verify track_run + cancel cancels the tracked task.

    :param broker: broker fixture.
    """
    fired: dict[str, bool] = {"cancelled": False}

    async def long_running() -> None:
        """Sleep until cancelled, recording the cancellation."""
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
    """Verify cancelling an unknown flow is a no-op.

    :param broker: broker fixture.
    """
    broker.cancel("T-ghost")  # must not raise


async def test_deliver_to_unregistered_flow_raises(broker):
    """Verify delivering to an unregistered flow raises KeyError.

    :param broker: broker fixture.
    """
    with pytest.raises(KeyError):
        await broker.deliver_hitl_answer("T-x", {"q": "y"})
