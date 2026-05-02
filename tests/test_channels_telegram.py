"""Tests for the Telegram long-poll adapter (`httpx.MockTransport`)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.schemas.channel import InboundMessage
from app.services.channels.adapters.telegram import TelegramAdapter


def _update(update_id: int, chat_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": chat_id, "is_bot": False, "first_name": "u"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 0,
            "text": text,
        },
    }


class _ScriptedTransport:
    """``httpx.MockTransport`` driver that returns scripted responses by URL."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._update_batches: list[list[dict[str, Any]]] = []
        self._send_responses: list[dict[str, Any]] = []

    def queue_updates(self, updates: list[dict[str, Any]]) -> None:
        self._update_batches.append(updates)

    def queue_send_ok(self) -> None:
        self._send_responses.append({"ok": True, "result": {"message_id": 1}})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "getUpdates" in request.url.path:
            if self._update_batches:
                batch = self._update_batches.pop(0)
            else:
                batch = []
            return httpx.Response(200, json={"ok": True, "result": batch})
        if "sendMessage" in request.url.path:
            if self._send_responses:
                payload = self._send_responses.pop(0)
            else:
                payload = {"ok": True, "result": {"message_id": 1}}
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"ok": False})


@pytest.fixture
def transport():
    return _ScriptedTransport()


def _adapter(transport: _ScriptedTransport, **kw: Any) -> TelegramAdapter:
    return TelegramAdapter(
        name="telegram",
        token="SECRET",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(transport.handler)
        ),
        poll_timeout=0,
        **kw,
    )


# ----------------------------------------------------------- inbound


async def test_long_poll_dispatches_each_update(transport):
    transport.queue_updates([_update(100, 42, "hi"), _update(101, 42, "ok")])
    received: list[InboundMessage] = []

    async def on_message(msg: InboundMessage) -> None:
        received.append(msg)

    adapter = _adapter(transport)
    await adapter.start(on_message)
    # Wait briefly for the poll loop to hit the queued batch.
    for _ in range(50):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.01)
    await adapter.stop()
    assert [m.text for m in received] == ["hi", "ok"]
    assert all(m.session_key == "42" for m in received)
    assert all(m.address == {"chat_id": 42} for m in received)
    assert all(m.channel == "telegram" for m in received)


async def test_offset_advances_after_batch(transport):
    transport.queue_updates([_update(50, 1, "a")])
    transport.queue_updates([_update(51, 1, "b")])
    received: list[str] = []

    async def on_message(msg: InboundMessage) -> None:
        received.append(msg.text)

    adapter = _adapter(transport)
    await adapter.start(on_message)
    for _ in range(80):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.01)
    await adapter.stop()
    assert received == ["a", "b"]
    # Last poll request should have offset = 52 (last update_id + 1).
    last_offset_req = next(
        r for r in reversed(transport.requests) if "getUpdates" in r.url.path
    )
    qs = dict(last_offset_req.url.params)
    assert qs.get("offset") == "52"


async def test_handler_exception_does_not_lose_offset(transport):
    transport.queue_updates([_update(100, 1, "boom"), _update(101, 1, "ok")])
    seen: list[str] = []

    async def on_message(msg: InboundMessage) -> None:
        if msg.text == "boom":
            raise RuntimeError("nope")
        seen.append(msg.text)

    adapter = _adapter(transport)
    await adapter.start(on_message)
    for _ in range(80):
        if seen:
            break
        await asyncio.sleep(0.01)
    await adapter.stop()
    # The handler raised on the first update but the offset must still
    # advance so the second update is delivered.
    assert seen == ["ok"]


# ----------------------------------------------------------- outbound


async def test_send_posts_to_send_message(transport):
    transport.queue_send_ok()
    adapter = _adapter(transport)
    await adapter.send({"chat_id": 42}, "hello")
    sent = [r for r in transport.requests if "sendMessage" in r.url.path]
    assert len(sent) == 1
    body = json.loads(sent[0].content)
    assert body == {"chat_id": 42, "text": "hello"}


# ----------------------------------------------------------- secrecy


async def test_token_not_logged_by_adapter(transport, caplog):
    """The adapter's own log records must not include the bot token.

    (Third-party loggers — notably ``httpx`` — DO log full URLs at INFO; that
    is a global-logging-config concern, not the adapter's responsibility. We
    scope the assertion to records the adapter itself emits.)
    """
    import logging

    caplog.set_level(logging.DEBUG, logger="app.services.channels.adapters.telegram")
    transport.queue_updates([_update(1, 1, "hi")])

    async def on_message(msg: InboundMessage) -> None:
        return None

    adapter = _adapter(transport)
    await adapter.start(on_message)
    await asyncio.sleep(0.05)
    await adapter.stop()
    for record in caplog.records:
        if record.name.startswith("app.services.channels.adapters.telegram"):
            assert "SECRET" not in record.getMessage()


async def test_stop_is_idempotent(transport):
    adapter = _adapter(transport)
    await adapter.start(lambda msg: asyncio.sleep(0))
    await adapter.stop()
    await adapter.stop()  # should not raise
