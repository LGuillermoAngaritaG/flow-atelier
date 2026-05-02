"""Tests for `schemas/channel.py` and `services/channels/base.py`.

The data shapes (`InboundMessage`, `ChannelConfig`, `ChannelBinding`) live in
`schemas/`. The runtime-checkable Protocol `ChannelAdapter` lives next to its
implementations in `services/channels/`.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import pytest
import yaml

from app.schemas.channel import ChannelBinding, ChannelConfig, InboundMessage
from app.services.channels.base import ChannelAdapter


def test_inbound_message_round_trip():
    msg = InboundMessage(
        channel="telegram",
        session_key="42",
        text="hi",
        address={"chat_id": 42},
        attachments=[],
    )
    restored = InboundMessage.model_validate(msg.model_dump())
    assert restored == msg


def test_inbound_message_defaults_attachments_empty():
    msg = InboundMessage(
        channel="telegram",
        session_key="42",
        text="hi",
        address={"chat_id": 42},
    )
    assert msg.attachments == []


def test_channel_config_minimal():
    raw = yaml.safe_load(
        """
        name: my_telegram
        kind: telegram
        token_env: TG_TOKEN
        """
    )
    cfg = ChannelConfig.model_validate(raw)
    assert cfg.name == "my_telegram"
    assert cfg.kind == "telegram"
    assert cfg.token_env == "TG_TOKEN"
    assert cfg.options == {}


def test_channel_config_with_options():
    cfg = ChannelConfig.model_validate(
        {
            "name": "my_discord",
            "kind": "discord",
            "token_env": "DISC_TOKEN",
            "options": {"intents": ["messages"]},
        }
    )
    assert cfg.options == {"intents": ["messages"]}


def test_channel_config_unknown_kind_rejected():
    with pytest.raises(Exception):
        ChannelConfig.model_validate(
            {"name": "x", "kind": "irc", "token_env": "X"}
        )


def test_channel_binding_round_trip():
    raw = yaml.safe_load(
        """
        channel: my_telegram
        conduit: echo
        """
    )
    binding = ChannelBinding.model_validate(raw)
    assert binding.channel == "my_telegram"
    assert binding.conduit == "echo"


# ----------------------------------------------------------- Protocol tests


class _FakeAdapter:
    """Minimal class that should structurally satisfy ChannelAdapter."""

    name = "fake"

    async def start(
        self, on_message: Callable[[InboundMessage], Awaitable[None]]
    ) -> None:
        return None

    async def send(self, address: dict[str, Any], text: str) -> None:
        return None

    async def stop(self) -> None:
        return None


class _IncompleteAdapter:
    """Missing send/stop — should NOT satisfy ChannelAdapter."""

    name = "broken"

    async def start(self, on_message):
        pass


def test_fake_adapter_satisfies_protocol():
    fake = _FakeAdapter()
    assert isinstance(fake, ChannelAdapter)


def test_incomplete_adapter_does_not_satisfy_protocol():
    broken = _IncompleteAdapter()
    assert not isinstance(broken, ChannelAdapter)
