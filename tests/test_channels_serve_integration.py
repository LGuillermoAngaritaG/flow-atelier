"""Integration tests for the Atelier facade's channels wiring."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import pytest
import yaml

from app.core.atelier import Atelier
from app.schemas.channel import InboundMessage
from app.services.channels.adapters import telegram as tg_module


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(tmp_path / "global"))
    monkeypatch.delenv("ATELIER_CHANNELS_CONFIG_PATH", raising=False)
    monkeypatch.setenv("TG_TOKEN", "fake-token")
    yield


def _write_faucet_conduit(atelier_dir, name: str = "echo") -> None:
    d = atelier_dir / "conduits" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "conduit.yaml").write_text(
        f"""
name: {name}
description: faucet
faucet: true
tasks:
  - chat:
      description: chat
      task: "respond to {{{{_message}}}}"
      tool: harness:claude-code
      depends_on: []
"""
    )


def _write_non_faucet_conduit(atelier_dir, name: str = "deploy") -> None:
    d = atelier_dir / "conduits" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "conduit.yaml").write_text(
        f"""
name: {name}
description: regular
tasks:
  - go:
      description: go
      task: "echo hi"
      tool: tool:bash
      depends_on: []
"""
    )


def _write_channels_yaml(atelier_dir, body: dict[str, Any]) -> None:
    atelier_dir.mkdir(parents=True, exist_ok=True)
    (atelier_dir / "channels.yaml").write_text(yaml.safe_dump(body))


# ----------------------------------------------------------- baseline


async def test_no_channels_yaml_means_no_channels(tmp_path):
    atelier = Atelier()
    assert atelier.channels_config is None
    await atelier.start_channels()
    assert atelier.channel_registry is None
    await atelier.stop_channels()  # no-op


# ----------------------------------------------------------- happy path


async def test_valid_channels_yaml_starts_adapter(tmp_path, monkeypatch):
    atelier_dir = tmp_path / ".atelier"
    _write_faucet_conduit(atelier_dir)
    _write_channels_yaml(
        atelier_dir,
        {
            "channels": [
                {"name": "telegram_bot", "kind": "telegram", "token_env": "TG_TOKEN"}
            ],
            "bindings": [{"channel": "telegram_bot", "conduit": "echo"}],
        },
    )

    starts: list[str] = []
    original_start = tg_module.TelegramAdapter.start

    async def _spy_start(self, on_message):
        starts.append(self.name)
        # Don't actually connect — our token is "fake-token". Simulate started.
        self._on_message = on_message

    monkeypatch.setattr(tg_module.TelegramAdapter, "start", _spy_start)
    monkeypatch.setattr(
        tg_module.TelegramAdapter, "stop", lambda self: asyncio.sleep(0)
    )

    atelier = Atelier()
    assert atelier.channels_config is not None
    await atelier.start_channels()
    assert starts == ["telegram_bot"]
    assert atelier.channel_registry is not None
    await atelier.stop_channels()


async def test_binding_to_missing_conduit_raises(tmp_path):
    atelier_dir = tmp_path / ".atelier"
    _write_channels_yaml(
        atelier_dir,
        {
            "channels": [
                {"name": "telegram_bot", "kind": "telegram", "token_env": "TG_TOKEN"}
            ],
            "bindings": [{"channel": "telegram_bot", "conduit": "ghost"}],
        },
    )
    atelier = Atelier()
    with pytest.raises(ValueError, match="ghost"):
        await atelier.start_channels()


async def test_binding_to_non_faucet_conduit_raises(tmp_path):
    atelier_dir = tmp_path / ".atelier"
    _write_non_faucet_conduit(atelier_dir, name="deploy")
    _write_channels_yaml(
        atelier_dir,
        {
            "channels": [
                {"name": "telegram_bot", "kind": "telegram", "token_env": "TG_TOKEN"}
            ],
            "bindings": [{"channel": "telegram_bot", "conduit": "deploy"}],
        },
    )
    atelier = Atelier()
    with pytest.raises(ValueError, match="faucet"):
        await atelier.start_channels()


async def test_missing_token_env_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    atelier_dir = tmp_path / ".atelier"
    _write_faucet_conduit(atelier_dir)
    _write_channels_yaml(
        atelier_dir,
        {
            "channels": [
                {"name": "telegram_bot", "kind": "telegram", "token_env": "TG_TOKEN"}
            ],
            "bindings": [{"channel": "telegram_bot", "conduit": "echo"}],
        },
    )
    atelier = Atelier()
    with pytest.raises(Exception, match="TG_TOKEN"):
        await atelier.start_channels()
