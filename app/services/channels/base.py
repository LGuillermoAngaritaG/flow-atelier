"""Structural contract every channel adapter implements.

The Protocol is ``runtime_checkable`` so the registry can validate adapters
without forcing inheritance — concrete adapters (Telegram via ``httpx``,
Discord via ``discord.py``) have nothing in common at the implementation
level beyond this shape.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from app.schemas.channel import InboundMessage


@runtime_checkable
class ChannelAdapter(Protocol):
    """Shape every channel adapter satisfies.

    All methods are async because adapters do network I/O. The registry owns
    the lifecycle: it calls ``start`` once with a dispatch callback, calls
    ``send`` zero or more times to reply, and calls ``stop`` exactly once on
    shutdown.
    """

    name: str

    async def start(
        self, on_message: Callable[[InboundMessage], Awaitable[None]]
    ) -> None:
        """Begin receiving messages, invoking ``on_message`` for each one."""
        ...

    async def send(self, address: dict[str, Any], text: str) -> None:
        """Send ``text`` to the addressed recipient."""
        ...

    async def stop(self) -> None:
        """Stop receiving; release any held resources (sockets, tasks)."""
        ...
