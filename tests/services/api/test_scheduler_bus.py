"""Unit tests for the SchedulerEventBus broadcast hub."""
from __future__ import annotations

import pytest

from app.services.api.scheduler_bus import SchedulerEventBus


async def test_broadcast_reaches_every_subscriber():
    """Verify every registered subscriber receives the same envelope."""
    bus = SchedulerEventBus()
    a: list[dict] = []
    b: list[dict] = []

    async def send_a(env):
        a.append(env)

    async def send_b(env):
        b.append(env)

    bus.subscribe(send_a)
    bus.subscribe(send_b)
    await bus.broadcast({"type": "scheduled_run_started", "flow_id": "f1"})
    assert a == [{"type": "scheduled_run_started", "flow_id": "f1"}]
    assert b == [{"type": "scheduled_run_started", "flow_id": "f1"}]


async def test_broadcast_with_no_subscribers_is_a_noop():
    """Verify broadcast on an empty bus does not raise."""
    bus = SchedulerEventBus()
    await bus.broadcast({"type": "scheduled_run_complete", "flow_id": "x"})


async def test_failing_subscriber_is_dropped_and_others_still_receive():
    """A subscriber that raises must be evicted, but siblings still get the envelope."""
    bus = SchedulerEventBus()
    survivor: list[dict] = []

    async def bad(env):
        raise RuntimeError("simulated socket gone")

    async def good(env):
        survivor.append(env)

    bus.subscribe(bad)
    bus.subscribe(good)
    await bus.broadcast({"type": "scheduled_run_failed"})
    assert survivor == [{"type": "scheduled_run_failed"}]
    # Second broadcast: bad has been evicted; good continues.
    await bus.broadcast({"type": "scheduled_task_event"})
    assert len(survivor) == 2


async def test_unsubscribe_removes_subscriber():
    """Verify unsubscribe stops the subscriber from getting further envelopes."""
    bus = SchedulerEventBus()
    seen: list[dict] = []

    async def send(env):
        seen.append(env)

    bus.subscribe(send)
    await bus.broadcast({"n": 1})
    bus.unsubscribe(send)
    await bus.broadcast({"n": 2})
    assert seen == [{"n": 1}]


async def test_subscribe_is_idempotent():
    """Subscribing the same callable twice should not duplicate deliveries."""
    bus = SchedulerEventBus()
    seen: list[dict] = []

    async def send(env):
        seen.append(env)

    bus.subscribe(send)
    bus.subscribe(send)
    await bus.broadcast({"n": 1})
    assert seen == [{"n": 1}]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
