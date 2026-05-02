"""`ChannelPromptSink` — `PromptSink` impl that talks to a chat channel.

A buffered sink: ``display`` accumulates text, ``flush`` sends one message.
Without buffering, Telegram users would get one notification per agent
token — unusable.

Permission requests are rendered as a numbered list ("1) Approve / 2) Deny")
and resolved when the registry hands the next inbound message text to
:meth:`deliver_permission_response`. The user's reply is parsed as a 1-based
index; empty / invalid replies fall back to option 1 (the safe default).

``request_input`` is intentionally unsupported — each channel message is
exactly one ACP turn (see SPEC §3 / plan Task 4). If anything ever wires this
sink into a non-faucet path, we want it to fail loudly.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.services.executor.prompt_sink import PermissionOption


SendCallable = Callable[[dict[str, Any], str], Awaitable[None]]


class ChannelPromptSink:
    """``PromptSink`` for chat channels.

    :param send: adapter callable that posts ``(address, text)`` to the
        underlying channel
    :param address: opaque address payload the adapter needs to reply (e.g.
        ``{"chat_id": 42}`` for Telegram); passed verbatim to ``send``
    """

    def __init__(self, send: SendCallable, address: dict[str, Any]) -> None:
        self._send = send
        self._address = address
        self._buffer: list[str] = []
        self._pending_permission: asyncio.Future[str] | None = None
        self._staged_response: str | None = None

    async def display(self, text: str) -> None:
        """Buffer ``text`` until :meth:`flush` is called."""
        self._buffer.append(text)

    async def flush(self) -> None:
        """Send all buffered text as a single message; reset the buffer."""
        if not self._buffer:
            return
        text = "".join(self._buffer)
        self._buffer.clear()
        await self._send(self._address, text)

    async def start_agent_turn(self, label: str = "agent") -> None:
        """No-op: channel renderings don't need turn dividers."""
        return None

    async def request_input(self, prompt: str) -> str:
        """Always raise — faucet conduits don't have within-turn user prompts."""
        raise RuntimeError(
            "ChannelPromptSink.request_input is not supported in faucet mode "
            "(each channel message is exactly one ACP turn)"
        )

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        """Render a numbered menu; resolve when the user's reply arrives."""
        if not options:
            raise ValueError("request_permission requires at least one option")

        lines = [summary]
        for idx, opt in enumerate(options, start=1):
            lines.append(f"  {idx}) {opt.label}")
        await self._send(self._address, "\n".join(lines))

        if self._staged_response is not None:
            raw = self._staged_response
            self._staged_response = None
        else:
            loop = asyncio.get_event_loop()
            self._pending_permission = loop.create_future()
            try:
                raw = await self._pending_permission
            finally:
                self._pending_permission = None

        return self._resolve_choice(raw, options)

    def deliver_permission_response(self, text: str) -> None:
        """Hand the user's reply to a pending permission prompt.

        If no prompt is active yet, the response is staged and consumed by the
        next ``request_permission`` call. Tests pre-stage; the registry
        delivers reactively when the next inbound message arrives.
        """
        if self._pending_permission is not None and not self._pending_permission.done():
            self._pending_permission.set_result(text)
            return
        self._staged_response = text

    @staticmethod
    def _resolve_choice(raw: str, options: list[PermissionOption]) -> str:
        cleaned = (raw or "").strip()
        if cleaned == "":
            return options[0].id
        try:
            choice = int(cleaned)
        except ValueError:
            return options[0].id
        if 1 <= choice <= len(options):
            return options[choice - 1].id
        return options[0].id
