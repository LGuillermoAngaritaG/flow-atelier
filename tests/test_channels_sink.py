"""Tests for `ChannelPromptSink` — buffered display + numbered permission menus.

Buffering matters: without it Telegram users would get one push notification
per agent token. The sink accumulates `display(text)` calls and flushes them
in a single `send(address, text)` call when the flow ends.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.channels.sink import ChannelPromptSink
from app.services.executor.prompt_sink import PermissionOption, PromptSink


class _RecordingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[dict[str, Any], str]] = []

    async def send(self, address: dict[str, Any], text: str) -> None:
        self.sent.append((address, text))


@pytest.fixture
def adapter():
    return _RecordingAdapter()


@pytest.fixture
def sink(adapter):
    return ChannelPromptSink(send=adapter.send, address={"chat_id": 7})


async def test_satisfies_prompt_sink_protocol(sink):
    assert isinstance(sink, PromptSink)


async def test_display_buffers_until_flush(sink, adapter):
    await sink.display("hello, ")
    await sink.display("world")
    assert adapter.sent == []
    await sink.flush()
    assert adapter.sent == [({"chat_id": 7}, "hello, world")]


async def test_flush_no_op_when_buffer_empty(sink, adapter):
    await sink.flush()
    assert adapter.sent == []


async def test_flush_clears_buffer(sink, adapter):
    await sink.display("first")
    await sink.flush()
    await sink.display("second")
    await sink.flush()
    assert adapter.sent == [
        ({"chat_id": 7}, "first"),
        ({"chat_id": 7}, "second"),
    ]


async def test_start_agent_turn_is_noop(sink, adapter):
    await sink.start_agent_turn("agent")
    assert adapter.sent == []


async def test_request_input_raises(sink):
    with pytest.raises(RuntimeError, match="faucet"):
        await sink.request_input("ignored")


async def test_request_permission_renders_numbered_menu(sink, adapter):
    options = [
        PermissionOption(id="ok", label="Approve"),
        PermissionOption(id="no", label="Deny"),
    ]
    # Pre-supply the user's choice so request_permission resolves immediately.
    sink.deliver_permission_response("2")
    chosen = await sink.request_permission("Run rm -rf /?", options)
    assert chosen == "no"
    assert len(adapter.sent) == 1
    _, body = adapter.sent[0]
    assert "Run rm -rf /?" in body
    assert "1) Approve" in body
    assert "2) Deny" in body


async def test_request_permission_default_is_first_on_empty_reply(sink):
    options = [
        PermissionOption(id="ok", label="Approve"),
        PermissionOption(id="no", label="Deny"),
    ]
    sink.deliver_permission_response("")
    chosen = await sink.request_permission("Run cmd?", options)
    assert chosen == "ok"


async def test_request_permission_invalid_choice_falls_back_to_default(sink):
    options = [
        PermissionOption(id="ok", label="Approve"),
        PermissionOption(id="no", label="Deny"),
    ]
    sink.deliver_permission_response("seven")
    chosen = await sink.request_permission("?", options)
    assert chosen == "ok"


async def test_request_permission_requires_options(sink):
    with pytest.raises(ValueError):
        await sink.request_permission("?", [])
