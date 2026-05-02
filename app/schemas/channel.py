"""Channel adapter data contracts.

These shapes cross the adapter ↔ registry boundary — they're data, not service
shapes — so they live in ``schemas/`` (matching ``TaskDefinition``'s placement).
The runtime-checkable Protocol that adapters implement lives next to its
implementations in ``app/services/channels/base.py``.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChannelKind(str, Enum):
    """Supported channel transports."""

    telegram = "telegram"
    discord = "discord"


class InboundMessage(BaseModel):
    """One message arriving from an external channel.

    :param channel: configured channel name (matches ``ChannelConfig.name``)
    :param session_key: per-sender key used for ACP session resume
        (e.g. ``str(chat_id)`` for Telegram, ``"<channel_id>:<author_id>"``
        for Discord)
    :param text: the user's message text (empty string if media-only)
    :param address: opaque payload the adapter needs to reply (e.g.
        ``{"chat_id": 42}`` for Telegram); registries pass it back to
        ``ChannelAdapter.send`` verbatim
    :param attachments: filesystem paths to downloaded media, if any
    """

    channel: str
    session_key: str
    text: str
    address: dict[str, Any]
    attachments: list[str] = Field(default_factory=list)


class ChannelConfig(BaseModel):
    """One entry under ``channels:`` in ``channels.yaml``.

    Tokens themselves are *never* persisted — adapters read the env var named
    in ``token_env`` at startup. ``options`` is adapter-specific and passed
    through opaquely (e.g. polling interval, gateway intents).
    """

    name: str
    kind: ChannelKind
    token_env: str
    options: dict[str, Any] = Field(default_factory=dict)


class ChannelBinding(BaseModel):
    """One entry under ``bindings:`` — links a channel to a faucet conduit."""

    channel: str
    conduit: str
