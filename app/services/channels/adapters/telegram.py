"""Telegram channel adapter — long-poll mode using the Bot API.

Uses ``httpx`` against ``getUpdates`` / ``sendMessage``. The client factory
is injected so tests can plug in ``httpx.MockTransport``; production paths
use the default ``httpx.AsyncClient``. Tokens are read from the environment
(``ChannelConfig.token_env``) at construction time and never logged.

Resilience: transient HTTP errors back off exponentially up to 30s. A
handler exception in ``on_message`` is logged and the offset is still
advanced so the bot doesn't get stuck replaying the same update forever.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import httpx

from app.schemas.channel import InboundMessage

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.telegram.org"
MAX_BACKOFF = 30.0


class TelegramAdapter:
    """Long-polling Telegram bot adapter.

    :param name: configured channel name (must match ``ChannelConfig.name``)
    :param token: bot token (sourced from env at config-load time)
    :param client_factory: optional ``() -> httpx.AsyncClient`` for tests
    :param poll_timeout: ``getUpdates`` long-poll timeout in seconds (0 in
        tests for fast loop iterations)
    :param api_base: override for the Bot API URL (default Telegram cloud)
    """

    def __init__(
        self,
        name: str,
        token: str,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        poll_timeout: int = 25,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        if not token:
            raise ValueError("telegram adapter requires a non-empty token")
        self.name = name
        self._token = token
        self._client_factory = client_factory or (lambda: httpx.AsyncClient())
        self._poll_timeout = poll_timeout
        self._base_url = f"{api_base.rstrip('/')}/bot{token}"
        self._client: httpx.AsyncClient | None = None
        self._task: asyncio.Task[None] | None = None
        self._on_message: Callable[[InboundMessage], Awaitable[None]] | None = None
        self._offset = 0
        self._stopping = False

    async def start(
        self, on_message: Callable[[InboundMessage], Awaitable[None]]
    ) -> None:
        """Begin the long-poll loop, dispatching each update to ``on_message``."""
        self._on_message = on_message
        self._client = self._client_factory()
        self._task = asyncio.create_task(self._poll_loop())

    async def send(self, address: dict[str, Any], text: str) -> None:
        """POST one ``sendMessage`` to the Bot API."""
        if self._client is None:
            self._client = self._client_factory()
        chat_id = address.get("chat_id")
        if chat_id is None:
            raise ValueError("telegram address must include chat_id")
        resp = await self._client.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        resp.raise_for_status()

    async def stop(self) -> None:
        """Stop the long-poll loop and close the HTTP client. Idempotent."""
        if self._stopping:
            return
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------- internals

    async def _poll_loop(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                updates = await self._fetch_updates()
                backoff = 1.0  # reset after success
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram getUpdates failed (will retry in %.1fs): %s",
                    backoff, type(exc).__name__,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue

            for upd in updates:
                self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
                await self._dispatch(upd)
            # Yield even when the transport returned synchronously (e.g.
            # httpx.MockTransport in tests); production long-polling already
            # blocks for ``poll_timeout`` seconds inside _fetch_updates.
            await asyncio.sleep(0)

    async def _fetch_updates(self) -> list[dict[str, Any]]:
        assert self._client is not None
        params: dict[str, Any] = {"timeout": self._poll_timeout}
        if self._offset > 0:
            params["offset"] = self._offset
        resp = await self._client.get(
            f"{self._base_url}/getUpdates",
            params=params,
            timeout=self._poll_timeout + 5,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(f"telegram getUpdates not-ok: {body!r}")
        return list(body.get("result", []))

    async def _dispatch(self, update: dict[str, Any]) -> None:
        msg = update.get("message")
        if not isinstance(msg, dict):
            return
        text = msg.get("text")
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return
        # We only deliver text messages in v1; media support is a follow-up.
        if not isinstance(text, str):
            return
        inbound = InboundMessage(
            channel=self.name,
            session_key=str(chat_id),
            text=text,
            address={"chat_id": chat_id},
            attachments=[],
        )
        assert self._on_message is not None
        try:
            await self._on_message(inbound)
        except Exception:  # noqa: BLE001
            logger.exception(
                "telegram on_message handler failed (offset advanced anyway)"
            )
