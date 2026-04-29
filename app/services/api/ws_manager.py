"""Per-connection WebSocket broker for ``/ws/run-conduit``.

Owns the per-connection state needed to multiplex multiple concurrent
flows over a single socket: a ``flow_id → asyncio.Queue`` map for HITL
answers, a ``flow_id → asyncio.Task`` map for run-task tracking and
cancel, and an outbound ``send`` callable.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


SendCallable = Callable[[dict[str, Any]], Awaitable[None]]


class WebSocketBroker:
    """Routes flow-scoped traffic over a single WebSocket connection.

    :param send: async callable receiving outbound JSON envelopes
    """

    def __init__(self, send: SendCallable) -> None:
        self.send_callable = send
        self._hitl_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    # ------------------------------------------------------------------ outbound

    async def send(self, payload: dict[str, Any]) -> None:
        """Forward ``payload`` to the wrapped sink."""
        await self.send_callable(payload)

    # ------------------------------------------------------------------ flow lifecycle

    def register_flow(self, flow_id: str) -> None:
        """Allocate per-flow state for ``flow_id`` (idempotent)."""
        self._hitl_queues.setdefault(flow_id, asyncio.Queue())

    def unregister_flow(self, flow_id: str) -> None:
        """Drop per-flow state for ``flow_id`` (idempotent)."""
        self._hitl_queues.pop(flow_id, None)
        self._tasks.pop(flow_id, None)

    # ------------------------------------------------------------------ HITL

    async def deliver_hitl_answer(
        self, flow_id: str, answers: dict[str, Any]
    ) -> None:
        """Push ``answers`` onto the queue the executor is awaiting.

        :raises KeyError: if no flow with that id has been registered
        """
        if flow_id not in self._hitl_queues:
            raise KeyError(flow_id)
        await self._hitl_queues[flow_id].put(answers)

    async def await_hitl_answer(
        self, flow_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Block until a matching ``hitl_answer`` arrives.

        :param flow_id: flow identifier
        :param timeout: optional seconds to wait before raising
            :class:`asyncio.TimeoutError`
        """
        if flow_id not in self._hitl_queues:
            self.register_flow(flow_id)
        queue = self._hitl_queues[flow_id]
        if timeout is None:
            return await queue.get()
        return await asyncio.wait_for(queue.get(), timeout=timeout)

    # ------------------------------------------------------------------ cancel

    def track_run(self, flow_id: str, task: asyncio.Task[Any]) -> None:
        """Record the asyncio task running ``flow_id`` so it can be cancelled."""
        self._tasks[flow_id] = task

    def cancel(self, flow_id: str) -> None:
        """Best-effort cancel of the run task for ``flow_id`` (no-op if unknown)."""
        task = self._tasks.get(flow_id)
        if task is not None and not task.done():
            task.cancel()
