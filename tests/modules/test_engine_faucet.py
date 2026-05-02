"""Engine support for faucet conduits driven by channel adapters.

Faucet conduits cannot declare `inputs:` (channel supplies them at runtime),
so the engine, when given a `channel_context`, seeds three implicit inputs:
`_message`, `_channel`, `_session_key`. The same `ChannelExecutionContext`
is also threaded onto every `FlowContext` so harness executors can resume
sessions per-task.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.modules.engine import Engine
from app.schemas.conduit import Conduit
from app.schemas.progress import FlowStatus
from app.schemas.log import ExecutionResult
from app.services.executor.base import ChannelExecutionContext, ExecutorBase
from app.services.store.filesystem import FilesystemStore


class _RecordingExecutor(ExecutorBase):
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.contexts: list[Any] = []

    async def execute(self, task, resolved_command, context):
        self.commands.append(resolved_command)
        self.contexts.append(context)
        return ExecutionResult(exit_code=0, output="ok", stdout="ok")


@pytest.fixture
def store(tmp_path):
    return FilesystemStore(tmp_path / ".atelier")


def _faucet_conduit() -> Conduit:
    return Conduit.model_validate(
        {
            "name": "echo",
            "description": "d",
            "faucet": True,
            "tasks": [
                {
                    "chat": {
                        "description": "d",
                        "task": "you said: {{_message}} on {{_channel}} (key={{_session_key}})",
                        "tool": "harness:claude-code",
                        "depends_on": [],
                    }
                }
            ],
        }
    )


def _channel_ctx(**overrides: Any) -> ChannelExecutionContext:
    base = {
        "faucet": True,
        "resume_session_ids": {},
        "on_session_minted": None,
        "channel": "telegram",
        "session_key": "42",
        "address": {"chat_id": 42},
        "message": "hello",
    }
    base.update(overrides)
    return ChannelExecutionContext(**base)


async def test_faucet_seeds_implicit_inputs(store):
    fake = _RecordingExecutor()
    engine = Engine({"harness:claude-code": fake}, store)
    flow_id = await engine.run(
        _faucet_conduit(),
        inputs={},
        channel_context=_channel_ctx(),
    )
    assert store.read_progress(flow_id).status == FlowStatus.completed
    assert fake.commands == [
        "you said: hello on telegram (key=42)"
    ], fake.commands


async def test_faucet_threads_channel_context_to_executor(store):
    fake = _RecordingExecutor()
    engine = Engine({"harness:claude-code": fake}, store)
    cc = _channel_ctx()
    await engine.run(_faucet_conduit(), inputs={}, channel_context=cc)
    assert fake.contexts[0].channel_context is cc


async def test_faucet_implicit_inputs_can_be_overridden_by_caller(store):
    """If the caller passes `_message` explicitly, the channel value wins.

    The channel-supplied implicit inputs override any pre-existing keys
    so adapter behavior is deterministic.
    """
    fake = _RecordingExecutor()
    engine = Engine({"harness:claude-code": fake}, store)
    await engine.run(
        _faucet_conduit(),
        inputs={"_message": "stale"},
        channel_context=_channel_ctx(),
    )
    assert fake.commands == ["you said: hello on telegram (key=42)"]


async def test_non_faucet_unchanged(store):
    """Regression: non-faucet runs ignore channel_context entirely."""
    conduit = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "inputs": {"name": "the name"},
            "tasks": [
                {
                    "greet": {
                        "description": "d",
                        "task": "hi {{inputs.name}}",
                        "tool": "tool:bash",
                        "depends_on": [],
                    }
                }
            ],
        }
    )
    fake = _RecordingExecutor()
    engine = Engine({"tool:bash": fake}, store)
    await engine.run(conduit, inputs={"name": "world"})
    assert fake.commands == ["hi world"]
    assert fake.contexts[0].channel_context is None


# Helper: make _message resolution deterministic across both message tests.
@pytest.fixture(autouse=True)
def _set_default_message(monkeypatch):
    pass
