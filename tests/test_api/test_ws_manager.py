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


async def test_cancel_all_cancels_every_tracked_run(broker):
    """Verify cancel_all cancels all tracked run tasks (disconnect cleanup).

    :param broker: broker fixture.
    """
    async def long_running() -> None:
        """Sleep until cancelled."""
        await asyncio.sleep(60)

    tasks = [asyncio.create_task(long_running()) for _ in range(3)]
    for i, task in enumerate(tasks):
        broker.track_run(f"T-{i}", task)
    await asyncio.sleep(0)
    broker.cancel_all()
    for task in tasks:
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_cancel_all_unblocks_hung_hitl_await(broker):
    """Verify cancel_all unblocks a run task parked on await_hitl_answer.

    Mirrors the disconnect case: a tool:hitl task awaits an answer with no
    timeout; the only socket that could deliver it is gone. Cancelling the
    tracked task must unwind that await rather than pin the run forever.

    :param broker: broker fixture.
    """
    broker.register_flow("T-hitl")

    async def parked_run() -> None:
        """Block forever awaiting an answer that never arrives."""
        await broker.await_hitl_answer("T-hitl")

    task = asyncio.create_task(parked_run())
    broker.track_run("T-hitl", task)
    await asyncio.sleep(0)
    assert not task.done()
    broker.cancel_all()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_await_hitl_answer_times_out(broker):
    """Verify await_hitl_answer raises TimeoutError when no answer arrives.

    :param broker: broker fixture.
    """
    broker.register_flow("T-1")
    with pytest.raises(asyncio.TimeoutError):
        await broker.await_hitl_answer("T-1", timeout=0.01)


async def test_late_answer_after_timeout_does_not_bleed_into_next_prompt(broker):
    """Verify a late answer arriving after a timeout is drained, not reused.

    If a human's answer lands on the queue just after the await times out, the
    next prompt for that flow must wait for a fresh answer rather than consuming
    the stale one.

    :param broker: broker fixture.
    """
    broker.register_flow("T-1")
    with pytest.raises(asyncio.TimeoutError):
        await broker.await_hitl_answer("T-1", timeout=0.01)
    # Late answer arrives after the timeout fired.
    await broker.deliver_hitl_answer("T-1", {"stale": True})
    # The next prompt must NOT see the stale answer; it should time out again.
    with pytest.raises(asyncio.TimeoutError):
        await broker.await_hitl_answer("T-1", timeout=0.01)


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


# ── agent-input requests (interactive harness turns) ──────────────────────


async def test_agent_input_request_id_is_opaque_and_unique(broker):
    """Verify each opened request gets its own opaque id.

    :param broker: broker fixture.
    """
    first, _ = broker.open_agent_input_request("T-1")
    second, _ = broker.open_agent_input_request("T-1")
    assert first != second
    # Opaque: carries neither the flow id nor a guessable counter.
    assert "T-1" not in first and first not in ("0", "1")


async def test_agent_input_answer_resolves_the_matching_future(broker):
    """Verify an answer resolves the future opened for that request.

    :param broker: broker fixture.
    """
    request_id, future = broker.open_agent_input_request("T-1")
    await broker.deliver_agent_input_answer("T-1", request_id, "blue")
    assert await future == "blue"


async def test_concurrent_requests_do_not_consume_each_others_answers(broker):
    """Verify two simultaneous prompts in one flow stay independent.

    :param broker: broker fixture.
    """
    id_a, future_a = broker.open_agent_input_request("T-1")
    id_b, future_b = broker.open_agent_input_request("T-1")

    await broker.deliver_agent_input_answer("T-1", id_b, "for-b")
    assert await future_b == "for-b"
    assert not future_a.done()

    await broker.deliver_agent_input_answer("T-1", id_a, "for-a")
    assert await future_a == "for-a"


async def test_agent_input_answer_for_unknown_request_raises(broker):
    """Verify an answer with an unknown request id raises KeyError.

    :param broker: broker fixture.
    """
    broker.open_agent_input_request("T-1")
    with pytest.raises(KeyError):
        await broker.deliver_agent_input_answer("T-1", "not-a-request", "x")


async def test_agent_input_answer_for_mismatched_flow_raises(broker):
    """Verify a valid request id under the wrong flow is rejected.

    :param broker: broker fixture.
    """
    request_id, future = broker.open_agent_input_request("T-1")
    with pytest.raises(KeyError):
        await broker.deliver_agent_input_answer("T-2", request_id, "x")
    assert not future.done()


async def test_answered_request_is_cleaned_up(broker):
    """Verify a request cannot be answered twice.

    :param broker: broker fixture.
    """
    request_id, _ = broker.open_agent_input_request("T-1")
    await broker.deliver_agent_input_answer("T-1", request_id, "blue")
    with pytest.raises(KeyError):
        await broker.deliver_agent_input_answer("T-1", request_id, "again")


async def test_close_agent_input_request_drops_pending_state(broker):
    """Verify closing a request removes it, so a late answer is rejected.

    :param broker: broker fixture.
    """
    request_id, _ = broker.open_agent_input_request("T-1")
    broker.close_agent_input_request("T-1", request_id)
    with pytest.raises(KeyError):
        await broker.deliver_agent_input_answer("T-1", request_id, "late")
    # Idempotent: closing again (e.g. from a finally after a failure) is a no-op.
    broker.close_agent_input_request("T-1", request_id)


async def test_unregister_flow_cancels_pending_agent_input(broker):
    """Verify unregistering a flow unblocks and drops its pending requests.

    :param broker: broker fixture.
    """
    request_id, future = broker.open_agent_input_request("T-1")
    broker.unregister_flow("T-1")
    assert future.cancelled() or future.done()
    with pytest.raises(KeyError):
        await broker.deliver_agent_input_answer("T-1", request_id, "late")
