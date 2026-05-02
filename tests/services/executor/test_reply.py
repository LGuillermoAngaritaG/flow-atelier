"""Tests for the ``tool:reply`` executor."""
from __future__ import annotations

from typing import Any

import pytest

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import FlowContext
from app.services.executor.reply import ReplyExecutor


class _FakeAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[dict[str, Any], str]] = []

    async def send(self, address: dict[str, Any], text: str) -> None:
        self.sent.append((address, text))


def _ctx() -> FlowContext:
    return FlowContext(flow_id="f", store=None, inputs={}, timeout=10)  # type: ignore[arg-type]


def _task(inputs: dict[str, Any]) -> TaskDefinition:
    return TaskDefinition(
        name="alert",
        description="d",
        task="ignored",
        tool=ToolType.reply,
        depends_on=[],
        inputs=inputs,
    )


async def test_reply_posts_to_named_channel():
    adapter = _FakeAdapter()
    executor = ReplyExecutor(adapters_provider=lambda: {"tg": adapter})
    task = _task(
        {"channel": "tg", "address": {"chat_id": 42}, "text": "deploy ok"}
    )
    result = await executor.execute(task, "ignored", _ctx())
    assert result.exit_code == 0
    assert adapter.sent == [({"chat_id": 42}, "deploy ok")]


async def test_reply_unknown_channel_fails_gracefully():
    executor = ReplyExecutor(adapters_provider=lambda: {})
    task = _task({"channel": "ghost", "address": {"chat_id": 1}, "text": "hi"})
    result = await executor.execute(task, "ignored", _ctx())
    assert result.exit_code == 1
    assert "ghost" in result.stderr


async def test_reply_missing_text_fails():
    adapter = _FakeAdapter()
    executor = ReplyExecutor(adapters_provider=lambda: {"tg": adapter})
    task = _task({"channel": "tg", "address": {"chat_id": 1}})
    result = await executor.execute(task, "ignored", _ctx())
    assert result.exit_code == 1
    assert "text" in result.stderr


async def test_reply_missing_address_fails():
    adapter = _FakeAdapter()
    executor = ReplyExecutor(adapters_provider=lambda: {"tg": adapter})
    task = _task({"channel": "tg", "text": "hi"})
    result = await executor.execute(task, "ignored", _ctx())
    assert result.exit_code == 1
    assert "address" in result.stderr


async def test_reply_adapter_send_error_surfaces():
    class _BoomAdapter:
        async def send(self, address, text):
            raise RuntimeError("network down")

    executor = ReplyExecutor(adapters_provider=lambda: {"tg": _BoomAdapter()})
    task = _task({"channel": "tg", "address": {"chat_id": 1}, "text": "hi"})
    result = await executor.execute(task, "ignored", _ctx())
    assert result.exit_code == 1
    assert "network down" in result.stderr


def test_tool_type_reply_validates():
    """Conduit schema accepts the new tool:reply tool type."""
    from app.schemas.conduit import Conduit

    conduit = Conduit.model_validate(
        {
            "name": "alerts",
            "description": "d",
            "tasks": [
                {
                    "alert": {
                        "description": "d",
                        "task": "send",
                        "tool": "tool:reply",
                        "depends_on": [],
                        "inputs": {"channel": "tg", "text": "hi"},
                    }
                }
            ],
        }
    )
    assert conduit.tasks[0].tool == ToolType.reply
