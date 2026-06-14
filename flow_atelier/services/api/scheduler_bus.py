"""App-level broadcast bus for scheduler envelopes.

The per-connection :class:`WebSocketBroker` fans events to a single socket
based on flow ownership. Scheduled fires don't belong to any one socket, so
we need a broadcast hub that every connected ``/ws/run-conduit`` client
subscribes to.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

SendCallable = Callable[[dict[str, Any]], Awaitable[None]]


class SchedulerEventBus:
    """Fan-out hub for scheduler-originated envelopes.

    Subscribers register an async send callable. ``broadcast(envelope)``
    delivers concurrently to every subscriber and silently drops any
    subscriber whose send raises (treated as a disconnect).
    """

    def __init__(self, send_timeout: float = 5.0) -> None:
        """Initialise with an empty subscriber set.

        :param send_timeout: max seconds to wait on a subscriber's send before
            treating it as a disconnect; bounds head-of-line blocking on the
            scheduler fire path so one stuck client can't pace dispatch.
        """
        self._subscribers: set[SendCallable] = set()
        self._send_timeout = send_timeout

    def subscribe(self, send: SendCallable) -> None:
        """Register ``send`` as a subscriber. Idempotent.

        :param send: async callable receiving outbound JSON envelopes
        """
        self._subscribers.add(send)

    def unsubscribe(self, send: SendCallable) -> None:
        """Remove ``send`` from the subscriber set. No-op when absent.

        :param send: send callable previously registered via subscribe
        """
        self._subscribers.discard(send)

    async def broadcast(self, envelope: dict[str, Any]) -> None:
        """Deliver ``envelope`` to every subscriber concurrently.

        Subscribers that raise are removed — a raise typically means the
        socket is gone. The bus must never propagate that failure back
        into the scheduler.

        :param envelope: JSON-serialisable envelope
        """
        if not self._subscribers:
            return
        snapshot = list(self._subscribers)
        results = await asyncio.gather(
            *(self._safe_send(sub, envelope) for sub in snapshot),
            return_exceptions=False,
        )
        for sub, ok in zip(snapshot, results, strict=True):
            if not ok:
                self._subscribers.discard(sub)

    async def _safe_send(self, send: SendCallable, envelope: dict[str, Any]) -> bool:
        """Invoke ``send`` (bounded by the timeout); True on success else False.

        A send that raises or exceeds ``send_timeout`` is treated as a dead
        subscriber and dropped, so a slow/backpressured socket can't stall the
        fire path.

        :param send: subscriber send callable
        :param envelope: envelope to deliver
        """
        try:
            await asyncio.wait_for(send(envelope), timeout=self._send_timeout)
            return True
        except Exception:  # noqa: BLE001 — includes TimeoutError
            logger.debug(
                "scheduler bus: dropping subscriber after send error/timeout",
                exc_info=True,
            )
            return False
