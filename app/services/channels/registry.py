"""`ChannelRegistry` — owns adapters, dispatches messages, serializes per key.

The registry is the brain of the channel runtime:

- holds the `ChannelAdapter` instances and starts/stops them with the lifespan;
- on each inbound message, looks up the bound conduit, builds a per-flow
  ``ChannelExecutionContext`` (with resume ids and an ``on_session_minted``
  callback that writes back to the store), and hands it to the runner;
- serializes messages within the same ``(channel, session_key)`` so two
  quick messages from the same user can't race the harness's resume id;
- handles the ``/new`` reset command without hitting the runner.

Single-process serve, so per-key locking is plain ``asyncio.Lock`` (no
inter-process coordination needed).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.schemas.channel import ChannelBinding, InboundMessage
from app.schemas.conduit import Conduit
from app.services.channels.base import ChannelAdapter
from app.services.channels.sessions import ChannelSessionStore
from app.services.executor.base import ChannelExecutionContext

logger = logging.getLogger(__name__)

RESET_COMMAND = "/new"
RESET_REPLY = "Session reset."

ConduitLookup = Callable[[str], Conduit | None]
RunnerCallable = Callable[[str, ChannelExecutionContext], Awaitable[Any]]


class ChannelRegistry:
    """Owns adapters and dispatches inbound messages to the runner."""

    def __init__(
        self,
        adapters: dict[str, ChannelAdapter],
        bindings: list[ChannelBinding],
        conduit_lookup: ConduitLookup,
        runner: RunnerCallable,
        session_store: ChannelSessionStore,
    ) -> None:
        self.adapters = adapters
        self.bindings = list(bindings)
        self._conduit_lookup = conduit_lookup
        self._runner = runner
        self._sessions = session_store
        self._binding_by_channel: dict[str, ChannelBinding] = {}
        self._key_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._started = False

    # ----------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Validate bindings, then call ``start()`` on every bound adapter."""
        if self._started:
            return
        for binding in self.bindings:
            if binding.channel not in self.adapters:
                raise ValueError(
                    f"binding references unknown channel {binding.channel!r}"
                )
            conduit = self._conduit_lookup(binding.conduit)
            if conduit is None:
                raise ValueError(
                    f"binding {binding.channel!r} -> {binding.conduit!r}: "
                    f"conduit not found"
                )
            if not conduit.faucet:
                raise ValueError(
                    f"binding {binding.channel!r} -> {binding.conduit!r}: "
                    f"conduit must be faucet=True"
                )
            self._binding_by_channel[binding.channel] = binding

        for name, adapter in self.adapters.items():
            await adapter.start(self._make_dispatch(name))
        self._started = True

    async def stop(self) -> None:
        """Stop every adapter; safe to call before or after ``start``."""
        if not self._started:
            return
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception:  # noqa: BLE001
                logger.exception("error stopping adapter %s", adapter.name)
        self._started = False

    # ----------------------------------------------------------- dispatch

    def _make_dispatch(
        self, channel_name: str
    ) -> Callable[[InboundMessage], Awaitable[None]]:
        async def _dispatch(msg: InboundMessage) -> None:
            await self._handle_message(channel_name, msg)

        return _dispatch

    async def _handle_message(self, channel_name: str, msg: InboundMessage) -> None:
        lock = self._key_locks.setdefault(
            (channel_name, msg.session_key), asyncio.Lock()
        )
        async with lock:
            await self._handle_locked(channel_name, msg)

    async def _handle_locked(
        self, channel_name: str, msg: InboundMessage
    ) -> None:
        adapter = self.adapters[channel_name]

        if msg.text.strip() == RESET_COMMAND:
            removed = self._sessions.clear_prefix(
                f"{channel_name}:{msg.session_key}:"
            )
            logger.info(
                "channel reset: channel=%s session_key=%s cleared=%d",
                channel_name, msg.session_key, removed,
            )
            await adapter.send(msg.address, RESET_REPLY)
            return

        binding = self._binding_by_channel.get(channel_name)
        if binding is None:
            logger.warning("dropping message: no binding for channel %r", channel_name)
            return
        conduit = self._conduit_lookup(binding.conduit)
        if conduit is None:
            logger.error(
                "dropping message: conduit %r vanished after start", binding.conduit
            )
            return

        resume_ids: dict[str, str] = {}
        for task in conduit.tasks:
            sid = self._sessions.get(
                f"{channel_name}:{msg.session_key}:{task.name}"
            )
            if sid is not None:
                resume_ids[task.name] = sid

        def _persist(task_name: str, session_id: str) -> None:
            self._sessions.set(
                f"{channel_name}:{msg.session_key}:{task_name}", session_id
            )

        cc = ChannelExecutionContext(
            faucet=True,
            resume_session_ids=resume_ids,
            on_session_minted=_persist,
            channel=channel_name,
            session_key=msg.session_key,
            address=msg.address,
            message=msg.text,
        )

        try:
            await self._runner(binding.conduit, cc)
        except Exception:  # noqa: BLE001
            # Channel adapters must not be torn down by one bad message.
            logger.exception(
                "runner failed for channel=%s session_key=%s",
                channel_name, msg.session_key,
            )
