"""Tests for the Discord gateway adapter.

Mocks ``discord.Client`` so we can verify the adapter wires inbound messages
to ``InboundMessage`` correctly without making a real gateway connection.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.schemas.channel import InboundMessage
from app.services.channels.adapters import discord as discord_adapter_module
from app.services.channels.adapters.discord import DiscordAdapter


class _FakeAuthor:
    def __init__(self, author_id: int, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


class _FakeMessage:
    def __init__(
        self, content: str, channel_id: int, author_id: int, bot: bool = False
    ) -> None:
        self.content = content
        self.channel = _FakeChannel(channel_id)
        self.author = _FakeAuthor(author_id, bot=bot)


class _FakeDiscordClient:
    """Stand-in for ``discord.Client`` capturing event handlers + send calls."""

    def __init__(self, *args, **kwargs) -> None:
        self._on_message = None
        self._on_ready = None
        self.started = False
        self.closed = False
        self._channels: dict[int, _FakeChannel] = {}

    def event(self, fn):
        """Mimic ``@client.event`` decorator: register by function name."""
        if fn.__name__ == "on_message":
            self._on_message = fn
        elif fn.__name__ == "on_ready":
            self._on_ready = fn
        return fn

    async def start(self, token: str) -> None:
        self.started = True
        # Park forever (gateway-style) until close() is called.
        await asyncio.Event().wait()

    async def close(self) -> None:
        self.closed = True

    def get_channel(self, channel_id: int) -> _FakeChannel:
        if channel_id not in self._channels:
            self._channels[channel_id] = _FakeChannel(channel_id)
        return self._channels[channel_id]


@pytest.fixture
def patched_client(monkeypatch):
    """Replace ``discord.Client`` with our fake for the duration of the test."""
    monkeypatch.setattr(
        discord_adapter_module,
        "_make_client",
        lambda intents=None: _FakeDiscordClient(),
    )


async def test_inbound_message_uses_channel_author_session_key(patched_client):
    received: list[InboundMessage] = []

    async def on_message(msg: InboundMessage) -> None:
        received.append(msg)

    adapter = DiscordAdapter(name="discord", token="SECRET")
    await adapter.start(on_message)
    # Simulate the gateway delivering a message.
    fake_msg = _FakeMessage(content="hello", channel_id=111, author_id=222)
    await adapter._client._on_message(fake_msg)
    await adapter.stop()

    assert len(received) == 1
    inbound = received[0]
    assert inbound.text == "hello"
    assert inbound.session_key == "111:222"
    assert inbound.address == {"channel_id": 111}
    assert inbound.channel == "discord"


async def test_messages_from_bots_are_ignored(patched_client):
    received: list[InboundMessage] = []

    async def on_message(msg: InboundMessage) -> None:
        received.append(msg)

    adapter = DiscordAdapter(name="discord", token="SECRET")
    await adapter.start(on_message)
    bot_msg = _FakeMessage(content="hi", channel_id=1, author_id=2, bot=True)
    await adapter._client._on_message(bot_msg)
    await adapter.stop()

    assert received == []


async def test_send_uses_channel_get_send(patched_client):
    adapter = DiscordAdapter(name="discord", token="SECRET")
    await adapter.start(lambda msg: asyncio.sleep(0))
    # Pre-create the channel so we can inspect what was sent.
    channel = adapter._client.get_channel(42)
    await adapter.send({"channel_id": 42}, "hi there")
    await adapter.stop()
    assert channel.sent == ["hi there"]


async def test_token_required():
    with pytest.raises(ValueError):
        DiscordAdapter(name="discord", token="")


async def test_stop_idempotent(patched_client):
    adapter = DiscordAdapter(name="discord", token="SECRET")
    await adapter.start(lambda msg: asyncio.sleep(0))
    await adapter.stop()
    await adapter.stop()
