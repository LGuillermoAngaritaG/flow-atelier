"""Tests for the `atelier channels` sub-app."""
from __future__ import annotations

import time

import pytest
import yaml
from typer.testing import CliRunner

from app.cli import app
from app.services.channels.sessions import ChannelSessionStore


@pytest.fixture
def fresh_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_channels_yaml(atelier_dir, body):
    atelier_dir.mkdir(parents=True, exist_ok=True)
    (atelier_dir / "channels.yaml").write_text(yaml.safe_dump(body))


def _write_faucet_conduit(atelier_dir, name="echo"):
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
      task: respond to {{{{_message}}}}
      tool: harness:claude-code
      depends_on: []
"""
    )


# ----------------------------------------------------------- list


def test_channels_list_with_no_yaml_reports_none(fresh_cwd):
    runner = CliRunner()
    result = runner.invoke(app, ["channels", "list"])
    assert result.exit_code == 0
    assert "no channels.yaml" in result.output.lower()


def test_channels_list_summarizes_yaml(fresh_cwd):
    atelier_dir = fresh_cwd / ".atelier"
    _write_faucet_conduit(atelier_dir)
    _write_channels_yaml(
        atelier_dir,
        {
            "channels": [
                {"name": "tg_bot", "kind": "telegram", "token_env": "TG_TOKEN"}
            ],
            "bindings": [{"channel": "tg_bot", "conduit": "echo"}],
        },
    )
    runner = CliRunner()
    result = runner.invoke(app, ["channels", "list"])
    assert result.exit_code == 0, result.output
    assert "tg_bot" in result.output
    assert "telegram" in result.output
    assert "echo" in result.output


# ----------------------------------------------------------- sessions


def test_channels_sessions_empty(fresh_cwd):
    runner = CliRunner()
    result = runner.invoke(app, ["channels", "sessions"])
    assert result.exit_code == 0
    assert "no sessions" in result.output.lower()


def test_channels_sessions_lists_entries(fresh_cwd):
    atelier_dir = fresh_cwd / ".atelier"
    store = ChannelSessionStore(atelier_dir=atelier_dir)
    store.set("telegram:42:chat", "abc")
    store.set("telegram:99:chat", "xyz")

    runner = CliRunner()
    result = runner.invoke(app, ["channels", "sessions"])
    assert result.exit_code == 0
    assert "telegram:42:chat" in result.output
    assert "telegram:99:chat" in result.output


# ----------------------------------------------------------- reset


def test_channels_reset_clears_matching_entries(fresh_cwd):
    atelier_dir = fresh_cwd / ".atelier"
    store = ChannelSessionStore(atelier_dir=atelier_dir)
    store.set("telegram:42:chat", "a")
    store.set("telegram:42:write", "b")
    store.set("telegram:99:chat", "c")

    runner = CliRunner()
    result = runner.invoke(app, ["channels", "reset", "42"])
    assert result.exit_code == 0
    assert "2" in result.output  # cleared count

    # Re-read the store to confirm.
    store2 = ChannelSessionStore(atelier_dir=atelier_dir)
    assert store2.get("telegram:42:chat") is None
    assert store2.get("telegram:42:write") is None
    assert store2.get("telegram:99:chat") == "c"


def test_channels_reset_no_match_reports_zero(fresh_cwd):
    atelier_dir = fresh_cwd / ".atelier"
    ChannelSessionStore(atelier_dir=atelier_dir)
    runner = CliRunner()
    result = runner.invoke(app, ["channels", "reset", "ghost"])
    assert result.exit_code == 0
    assert "0" in result.output
