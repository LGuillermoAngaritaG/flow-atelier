"""Tests for `ChannelSessionStore` — atomic JSON store with TTL + prefix clear.

Persists `{ "<channel>:<session_key>:<task>": {session_id, last_active_at} }`
to `<atelier_dir>/channel_sessions.json`. Single-process, atomic writes.
"""
from __future__ import annotations

import json
import time

import pytest

from app.services.channels.sessions import ChannelSessionStore


@pytest.fixture
def store(tmp_path):
    return ChannelSessionStore(atelier_dir=tmp_path)


def test_get_missing_returns_none(store):
    assert store.get("telegram:42:chat") is None


def test_set_then_get_roundtrip(store):
    store.set("telegram:42:chat", "sess-abc")
    assert store.get("telegram:42:chat") == "sess-abc"


def test_set_creates_file_atomically(tmp_path, store):
    store.set("telegram:42:chat", "sess-abc")
    path = tmp_path / "channel_sessions.json"
    assert path.exists()
    assert not (tmp_path / "channel_sessions.json.tmp").exists()
    data = json.loads(path.read_text())
    entry = data["sessions"]["telegram:42:chat"]
    assert entry["session_id"] == "sess-abc"
    assert isinstance(entry["last_active_at"], (int, float))


def test_set_bumps_last_active_at(store):
    store.set("telegram:42:chat", "sess-1")
    first = store._read_all()["telegram:42:chat"]["last_active_at"]
    time.sleep(0.01)
    store.set("telegram:42:chat", "sess-1")
    second = store._read_all()["telegram:42:chat"]["last_active_at"]
    assert second > first


def test_set_overwrites_session_id(store):
    store.set("telegram:42:chat", "sess-1")
    store.set("telegram:42:chat", "sess-2")
    assert store.get("telegram:42:chat") == "sess-2"


def test_get_returns_none_when_expired(tmp_path):
    short_store = ChannelSessionStore(atelier_dir=tmp_path, ttl_seconds=1)
    short_store.set("telegram:42:chat", "sess-abc")
    time.sleep(1.1)
    assert short_store.get("telegram:42:chat") is None


def test_default_ttl_is_48_hours(store):
    assert store.ttl_seconds == 48 * 3600


def test_clear_prefix_removes_matching_entries(store):
    store.set("telegram:42:chat", "s1")
    store.set("telegram:42:write", "s2")
    store.set("telegram:99:chat", "s3")
    store.set("discord:42:chat", "s4")

    store.clear_prefix("telegram:42:")

    assert store.get("telegram:42:chat") is None
    assert store.get("telegram:42:write") is None
    assert store.get("telegram:99:chat") == "s3"
    assert store.get("discord:42:chat") == "s4"


def test_clear_prefix_returns_count(store):
    store.set("telegram:42:a", "s1")
    store.set("telegram:42:b", "s2")
    store.set("telegram:99:a", "s3")

    removed = store.clear_prefix("telegram:42:")

    assert removed == 2


def test_clear_prefix_no_matches_returns_zero(store):
    store.set("telegram:42:a", "s1")
    assert store.clear_prefix("nope:") == 0
    assert store.get("telegram:42:a") == "s1"


def test_corrupt_file_does_not_crash_get(tmp_path):
    (tmp_path / "channel_sessions.json").write_text("{not valid json")
    store = ChannelSessionStore(atelier_dir=tmp_path)
    assert store.get("telegram:42:chat") is None


def test_corrupt_file_recovers_on_set(tmp_path):
    (tmp_path / "channel_sessions.json").write_text("garbage")
    store = ChannelSessionStore(atelier_dir=tmp_path)
    store.set("telegram:42:chat", "sess-abc")
    assert store.get("telegram:42:chat") == "sess-abc"


def test_atelier_dir_is_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    store = ChannelSessionStore(atelier_dir=nested)
    store.set("k", "s1")
    assert (nested / "channel_sessions.json").exists()
