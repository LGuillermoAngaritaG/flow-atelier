"""Discord channel adapter — gateway mode using ``discord.py``.

Gateway connections are persistent; the adapter parks the client task for
the lifetime of ``serve`` and cancels it on stop. Inbound messages map to
``InboundMessage`` with ``session_key="<channel_id>:<author_id>"`` (per
SPEC §3 resolved Q3 — DM-feel default for shared channels).

The ``_make_client`` factory is the test seam: tests replace it with a fake
that captures event handlers without making a real connection.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import discord  # type: ignore[import-untyped]

from app.schemas.channel import InboundMessage

logger = logging.getLogger(__name__)


def _make_client(intents=None):  # pragma: no cover — replaced in tests
    if intents is None:
        intents = discord.Intents.default()
        intents.message_content = True
    return discord.Client(intents=intents)


class DiscordAdapter:
    """`discord.py`-backed adapter for Discord text channels."""

    def __init__(
        self,
        name: str,
        token: str,
    ) -> None:
        if not token:
            raise ValueError("discord adapter requires a non-empty token")
        self.name = name
        self._token = token
        self._client = None
        self._task: asyncio.Task[None] | None = None
        self._on_message: Callable[[InboundMessage], Awaitable[None]] | None = None
        self._stopping = False

    async def start(
        self, on_message: Callable[[InboundMessage], Awaitable[None]]
    ) -> None:
        """Connect to the gateway and route incoming messages to ``on_message``."""
        self._on_message = on_message
        self._client = _make_client()

        @self._client.event
        async def on_message(message):
            await self._handle(message)

        self._task = asyncio.create_task(self._client.start(self._token))

    async def send(self, address: dict[str, Any], text: str) -> None:
        """Post ``text`` to the discord channel identified by ``address``."""
        channel_id = address.get("channel_id")
        if channel_id is None:
            raise ValueError("discord address must include channel_id")
        if self._client is None:
            raise RuntimeError("discord adapter not started")
        channel = self._client.get_channel(int(channel_id))
        if channel is None:
            raise RuntimeError(
                f"discord channel {channel_id!r} not found in client cache"
            )
        await channel.send(text)

    async def stop(self) -> None:
        """Close the gateway connection. Idempotent."""
        if self._stopping:
            return
        self._stopping = True
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                logger.exception("error closing discord client")
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _handle(self, message: Any) -> None:
        # Ignore the bot's own messages (or any other bot's) — would cause
        # infinite reply loops.
        if getattr(message.author, "bot", False):
            return
        text = getattr(message, "content", "")
        channel_id = message.channel.id
        author_id = message.author.id
        inbound = InboundMessage(
            channel=self.name,
            session_key=f"{channel_id}:{author_id}",
            text=text,
            address={"channel_id": channel_id},
            attachments=[],
        )
        assert self._on_message is not None
        try:
            await self._on_message(inbound)
        except Exception:  # noqa: BLE001
            logger.exception(
                "discord on_message handler failed (ack'd to gateway anyway)"
            )
