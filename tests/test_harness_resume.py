"""Tests for the harness's resume-session-id + faucet-mode plumbing.

Faucet mode (driven by a chat channel) needs three things on top of the
existing ``AcpHarnessExecutor``:

1. When a per-(channel, session_key, task) ACP session id already exists,
   ``conn.load_session`` should be called instead of ``conn.new_session``.
2. The registry needs to learn the session id (whether minted or resumed)
   so it can persist it for the next message — via ``on_session_minted``.
3. No ``[ATELIER_DONE]`` suffix in faucet mode: each message is exactly one
   ACP turn, so ``task.interactive`` is overridden.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import ChannelExecutionContext, FlowContext
from app.services.executor.harness import AcpHarnessExecutor


FAKE_AGENT = Path(__file__).resolve().parent / "fixtures" / "fake_acp_agent.py"


class _SilentSink:
    """Sink that swallows everything — keeps test output clean."""

    async def display(self, text: str) -> None:
        return None

    async def start_agent_turn(self, label: str = "agent") -> None:
        return None

    async def request_input(self, prompt: str) -> str:
        raise RuntimeError("not used in faucet mode")

    async def request_permission(self, summary, options) -> str:
        return options[0].id


def _fake_cmd(script: dict[str, Any]) -> list[str]:
    return [sys.executable, str(FAKE_AGENT), "--script", json.dumps(script)]


def _task(prompt: str, *, interactive: bool = False) -> TaskDefinition:
    return TaskDefinition(
        name="chat",
        description="d",
        task=prompt,
        tool=ToolType.claude,
        depends_on=[],
        interactive=interactive,
    )


def _ctx(channel_context: ChannelExecutionContext | None = None) -> FlowContext:
    return FlowContext(
        flow_id="fake",
        store=None,  # type: ignore[arg-type]
        inputs={},
        timeout=30,
        channel_context=channel_context,
    )


async def test_no_channel_context_behaves_like_before():
    """With no channel context, behavior is unchanged."""
    script = {"turns": [{"chunks": ["hello"], "stop": "end_turn"}]}
    harness = AcpHarnessExecutor(launch_cmd=_fake_cmd(script), sink=_SilentSink())
    result = await harness.execute(_task("hi"), "hi", _ctx())
    assert result.exit_code == 0
    assert "hello" in result.output


async def test_on_session_minted_called_when_no_resume_id():
    """Mint a fresh session — callback fires with the new session id."""
    minted: list[tuple[str, str]] = []
    ctx = _ctx(
        ChannelExecutionContext(
            faucet=True,
            resume_session_ids={},
            on_session_minted=lambda task_name, sid: minted.append((task_name, sid)),
        )
    )
    script = {"turns": [{"chunks": ["ok"], "stop": "end_turn"}]}
    harness = AcpHarnessExecutor(launch_cmd=_fake_cmd(script), sink=_SilentSink())
    result = await harness.execute(_task("hi"), "hi", ctx)
    assert result.exit_code == 0
    assert minted == [("chat", "fake-session-1")]


async def test_faucet_mode_does_not_loop_on_interactive_task():
    """In faucet mode, task.interactive is overridden — exactly one turn."""
    ctx = _ctx(
        ChannelExecutionContext(
            faucet=True,
            resume_session_ids={},
            on_session_minted=lambda task_name, sid: None,
        )
    )
    # task.interactive=True would normally trigger the done-marker loop.
    # In faucet mode, the harness must run exactly one turn instead.
    task = _task("hi", interactive=True)
    script = {"turns": [{"chunks": ["one-shot reply"], "stop": "end_turn"}]}
    harness = AcpHarnessExecutor(launch_cmd=_fake_cmd(script), sink=_SilentSink())
    result = await harness.execute(task, "hi", ctx)
    # If the loop had been engaged, the result would have stderr "no done
    # marker" and exit_code=1.
    assert result.exit_code == 0
    assert "one-shot reply" in result.output


async def test_resume_session_id_passed_through_callback():
    """When a resume id is configured, callback reports the resumed id."""
    minted: list[tuple[str, str]] = []
    ctx = _ctx(
        ChannelExecutionContext(
            faucet=True,
            resume_session_ids={"chat": "resumed-xyz"},
            on_session_minted=lambda task_name, sid: minted.append((task_name, sid)),
        )
    )
    script = {"turns": [{"chunks": ["resumed"], "stop": "end_turn"}]}
    harness = AcpHarnessExecutor(launch_cmd=_fake_cmd(script), sink=_SilentSink())
    result = await harness.execute(_task("hi"), "hi", ctx)
    # The fake agent's load_session is a no-op stub; the harness should still
    # use the resume id verbatim and report it via on_session_minted.
    assert result.exit_code == 0
    assert minted == [("chat", "resumed-xyz")]


async def test_faucet_mode_skips_done_marker_suffix():
    """Faucet mode does NOT append the [ATELIER_DONE] interactive suffix."""
    ctx = _ctx(
        ChannelExecutionContext(
            faucet=True,
            resume_session_ids={},
            on_session_minted=lambda task_name, sid: None,
        )
    )
    # Mark the task interactive — non-faucet behavior would append the suffix.
    task = _task("hi there", interactive=True)
    script = {"turns": [{"chunks": ["resp"], "stop": "end_turn"}]}
    harness = AcpHarnessExecutor(launch_cmd=_fake_cmd(script), sink=_SilentSink())
    # If the harness errantly appended the marker suffix, the agent receives
    # a much longer prompt — but we can't observe that from outside. Instead
    # we observe: the result is clean (no marker leakage in output).
    result = await harness.execute(task, "hi there", ctx)
    assert result.exit_code == 0
    assert "[ATELIER_DONE]" not in result.output
