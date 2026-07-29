"""Per-connection WebSocket broker for ``/ws/run-conduit``.

Owns the per-connection state needed to multiplex multiple concurrent
flows over a single socket: a ``flow_id → asyncio.Queue`` map for HITL
answers, a ``flow_id → {request_id: Future}`` map for interactive
agent-input turns, a ``flow_id → asyncio.Task`` map for run-task tracking
and cancel, and an outbound ``send`` callable.
"""
from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

SendCallable = Callable[[dict[str, Any]], Awaitable[None]]


class WebSocketBroker:
    """Routes flow-scoped traffic over a single WebSocket connection.

    :param send: async callable receiving outbound JSON envelopes
    """

    def __init__(self, send: SendCallable) -> None:
        """Initialise the broker bound to an outbound JSON sink.

        :param send: async callable receiving outbound JSON envelopes
        """
        self.send_callable = send
        self._hitl_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        # Interactive agent turns awaiting a reply, keyed flow -> request id.
        # A future per request rather than a queue per flow: two interactive
        # tasks in one flow can be waiting at the same time, and a queue would
        # hand the first answer to whichever happened to be listening.
        self._agent_requests: dict[str, dict[str, asyncio.Future[str]]] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        # Flows whose last answer-await timed out. An answer for the abandoned
        # prompt can still arrive afterwards; we drain it at the start of the
        # next await so it can't satisfy a different question (see
        # ``await_hitl_answer``).
        self._timed_out: set[str] = set()

    # ------------------------------------------------------------------ outbound

    async def send(self, payload: dict[str, Any]) -> None:
        """Forward ``payload`` to the wrapped sink.

        :param payload: JSON-serialisable envelope to send
        """
        await self.send_callable(payload)

    # ------------------------------------------------------------------ flow lifecycle

    def register_flow(self, flow_id: str) -> None:
        """Allocate per-flow state for ``flow_id`` (idempotent).

        :param flow_id: flow identifier
        """
        self._hitl_queues.setdefault(flow_id, asyncio.Queue())

    def unregister_flow(self, flow_id: str) -> None:
        """Drop per-flow state for ``flow_id`` (idempotent).

        Pending agent-input requests are cancelled rather than dropped: the
        flow is over, so nothing will ever answer them, and a sink still
        awaiting one would hang.

        :param flow_id: flow identifier
        """
        self._hitl_queues.pop(flow_id, None)
        for future in self._agent_requests.pop(flow_id, {}).values():
            if not future.done():
                future.cancel()
        self._tasks.pop(flow_id, None)
        self._timed_out.discard(flow_id)

    # ------------------------------------------------------------------ HITL

    async def deliver_hitl_answer(
        self, flow_id: str, answers: dict[str, Any]
    ) -> None:
        """Push ``answers`` onto the queue the executor is awaiting.

        :param flow_id: flow identifier
        :param answers: collected HITL answers keyed by input name
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
        if flow_id in self._timed_out:
            # The previous await for this flow timed out; a stale answer for
            # that abandoned prompt may have arrived since. Discard it so this
            # fresh prompt waits for its own answer rather than consuming the
            # old one. The executor always sends a new request before awaiting,
            # so anything queued here cannot be a reply to the current prompt.
            self._timed_out.discard(flow_id)
            while not queue.empty():
                queue.get_nowait()
        if timeout is None:
            return await queue.get()
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            self._timed_out.add(flow_id)
            raise

    # ------------------------------------------------------------------ agent input

    def open_agent_input_request(
        self, flow_id: str
    ) -> tuple[str, asyncio.Future[str]]:
        """Register a pending interactive turn and return its id and future.

        :param flow_id: flow identifier the prompt belongs to
        :returns: tuple of the opaque request id and the future its answer
            will resolve.
        """
        request_id = secrets.token_hex(8)
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._agent_requests.setdefault(flow_id, {})[request_id] = future
        return request_id, future

    async def deliver_agent_input_answer(
        self, flow_id: str, request_id: str, answer: str
    ) -> None:
        """Resolve the request ``request_id`` is waiting on with ``answer``.

        :param flow_id: flow identifier the answer claims to belong to
        :param request_id: the id issued with the request
        :param answer: the user's reply for that turn
        :raises KeyError: if the request is unknown, already answered, or
            registered under a different flow
        """
        future = self._agent_requests.get(flow_id, {}).pop(request_id, None)
        if future is None:
            raise KeyError(request_id)
        if not future.done():
            future.set_result(answer)

    def close_agent_input_request(self, flow_id: str, request_id: str) -> None:
        """Forget a pending request (idempotent).

        Called from the waiter's ``finally``, so a turn that was answered,
        cancelled or failed leaves no entry a late answer could resolve.

        :param flow_id: flow identifier the request belongs to
        :param request_id: the id issued with the request
        """
        pending = self._agent_requests.get(flow_id)
        if pending is None:
            return
        pending.pop(request_id, None)
        if not pending:
            self._agent_requests.pop(flow_id, None)

    # ------------------------------------------------------------------ cancel

    def track_run(self, flow_id: str, task: asyncio.Task[Any]) -> None:
        """Record the asyncio task running ``flow_id`` so it can be cancelled.

        :param flow_id: flow identifier
        :param task: asyncio task driving the run
        """
        self._tasks[flow_id] = task

    def cancel(self, flow_id: str) -> None:
        """Best-effort cancel of the run task for ``flow_id`` (no-op if unknown).

        :param flow_id: flow identifier
        """
        task = self._tasks.get(flow_id)
        if task is not None and not task.done():
            task.cancel()

    def cancel_all(self) -> None:
        """Cancel every tracked run task (best-effort).

        Called when the WebSocket disconnects: without this an in-flight run
        keeps executing detached, and a ``tool:hitl`` task blocked on an answer
        that can no longer arrive would pin the run forever. Cancelling the
        driving task unwinds ``engine.run`` and unblocks that await.
        """
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
