"""``tool:reply`` executor — non-conversational sends via channel adapters.

Used by cron-fired summaries, deploy alerts, and similar one-shot
notifications. Orthogonal to faucet conduits — there's no inbound message,
no session resume, just "post this text to that channel."

Inputs:

- ``channel`` (str) — configured channel name (must match an entry in
  ``channels.yaml``)
- ``address`` (dict) — adapter-specific payload (e.g. ``{"chat_id": 42}``
  for Telegram, ``{"channel_id": 1234}`` for Discord)
- ``text`` (str) — the message body
"""
from __future__ import annotations

from typing import Any, Callable

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.channels.base import ChannelAdapter
from app.services.executor.base import ExecutorBase, FlowContext


AdaptersProvider = Callable[[], dict[str, ChannelAdapter]]


class ReplyExecutor(ExecutorBase):
    """Posts ``inputs.text`` to ``inputs.address`` on ``inputs.channel``."""

    def __init__(self, adapters_provider: AdaptersProvider) -> None:
        self._adapters_provider = adapters_provider

    async def execute(
        self,
        task: TaskDefinition,
        resolved_command: str,
        context: FlowContext,
    ) -> ExecutionResult:
        del resolved_command, context  # we read everything from task.inputs
        inputs = task.inputs

        channel_name = inputs.get("channel")
        address = inputs.get("address")
        text = inputs.get("text")

        if not isinstance(channel_name, str) or not channel_name:
            return _err("tool:reply requires inputs.channel (string)")
        if not isinstance(text, str):
            return _err("tool:reply requires inputs.text (string)")
        if not isinstance(address, dict):
            return _err("tool:reply requires inputs.address (dict)")

        adapters = self._adapters_provider()
        adapter = adapters.get(channel_name)
        if adapter is None:
            return _err(f"tool:reply: channel {channel_name!r} not configured")

        try:
            await adapter.send(address, text)
        except Exception as exc:  # noqa: BLE001
            return _err(f"tool:reply send failed: {type(exc).__name__}: {exc}")

        return ExecutionResult(exit_code=0, stdout="sent", output="sent")


def _err(msg: str) -> ExecutionResult:
    return ExecutionResult(exit_code=1, stderr=msg, output="")
