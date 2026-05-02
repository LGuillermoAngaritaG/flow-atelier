"""Tests for `ChannelRegistry` — dispatch, FIFO, /new, TTL, binding validation."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import pytest

from app.schemas.channel import (
    ChannelBinding,
    ChannelConfig,
    ChannelKind,
    InboundMessage,
)
from app.schemas.conduit import Conduit
from app.services.channels.registry import ChannelRegistry
from app.services.channels.sessions import ChannelSessionStore


class FakeAdapter:
    """In-memory `ChannelAdapter` for tests."""

    def __init__(self, name: str = "telegram") -> None:
        self.name = name
        self.sent: list[tuple[dict[str, Any], str]] = []
        self._on_message: Callable[[InboundMessage], Awaitable[None]] | None = None
        self.started = False
        self.stopped = False

    async def start(self, on_message):
        self._on_message = on_message
        self.started = True

    async def send(self, address: dict[str, Any], text: str) -> None:
        self.sent.append((address, text))

    async def stop(self) -> None:
        self.stopped = True

    async def deliver(self, msg: InboundMessage) -> None:
        assert self._on_message is not None, "start() not called yet"
        await self._on_message(msg)


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
                        "task": "respond to {{_message}}",
                        "tool": "harness:claude-code",
                        "depends_on": [],
                    }
                }
            ],
        }
    )


def _non_faucet_conduit() -> Conduit:
    return Conduit.model_validate(
        {
            "name": "deploy",
            "description": "d",
            "tasks": [
                {
                    "go": {
                        "description": "d",
                        "task": "echo hi",
                        "tool": "tool:bash",
                        "depends_on": [],
                    }
                }
            ],
        }
    )


@pytest.fixture
def store(tmp_path):
    return ChannelSessionStore(atelier_dir=tmp_path)


def _make_registry(
    *,
    adapters: dict[str, FakeAdapter],
    bindings: list[ChannelBinding],
    conduit_lookup: dict[str, Conduit],
    runner=None,
    store: ChannelSessionStore | None = None,
    tmp_path=None,
) -> ChannelRegistry:
    if store is None:
        store = ChannelSessionStore(atelier_dir=tmp_path)
    if runner is None:
        async def _noop(name, channel_context):
            return None
        runner = _noop
    return ChannelRegistry(
        adapters=adapters,
        bindings=bindings,
        conduit_lookup=conduit_lookup.get,
        runner=runner,
        session_store=store,
    )


# ----------------------------------------------------------- start validation


async def test_start_rejects_unknown_conduit(store):
    adapter = FakeAdapter()
    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="missing")],
        conduit_lookup={},
        store=store,
    )
    with pytest.raises(ValueError, match="missing"):
        await reg.start()


async def test_start_rejects_non_faucet_conduit(store):
    adapter = FakeAdapter()
    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="deploy")],
        conduit_lookup={"deploy": _non_faucet_conduit()},
        store=store,
    )
    with pytest.raises(ValueError, match="faucet"):
        await reg.start()


async def test_start_rejects_binding_to_unknown_channel(store):
    reg = _make_registry(
        adapters={},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        store=store,
    )
    with pytest.raises(ValueError, match="telegram"):
        await reg.start()


async def test_start_calls_adapter_start(store):
    adapter = FakeAdapter()
    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        store=store,
    )
    await reg.start()
    assert adapter.started is True
    await reg.stop()
    assert adapter.stopped is True


# ----------------------------------------------------------- dispatch


async def test_message_routed_to_runner(store):
    adapter = FakeAdapter()
    runner_calls: list[tuple[str, Any]] = []

    async def runner(name: str, channel_context):
        runner_calls.append((name, channel_context))

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=runner,
        store=store,
    )
    await reg.start()
    msg = InboundMessage(
        channel="telegram", session_key="42", text="hi", address={"chat_id": 42}
    )
    await adapter.deliver(msg)
    await reg.stop()
    assert len(runner_calls) == 1
    name, cc = runner_calls[0]
    assert name == "echo"
    assert cc.faucet is True
    assert cc.message == "hi"
    assert cc.session_key == "42"
    assert cc.channel == "telegram"
    assert cc.address == {"chat_id": 42}


async def test_resume_session_id_provided_to_runner(store):
    """If a session id exists for this (channel, session_key, task), it is read."""
    store.set("telegram:42:chat", "resumed-abc")
    adapter = FakeAdapter()
    captured: list[Any] = []

    async def runner(name: str, channel_context):
        captured.append(channel_context)

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=runner,
        store=store,
    )
    await reg.start()
    await adapter.deliver(
        InboundMessage(
            channel="telegram", session_key="42", text="hi", address={"chat_id": 42}
        )
    )
    await reg.stop()
    assert captured[0].resume_session_ids == {"chat": "resumed-abc"}


async def test_on_session_minted_persists_id(store):
    """The runner's on_session_minted callback writes to the session store."""
    adapter = FakeAdapter()

    async def runner(name: str, channel_context):
        # Simulate the harness reporting a freshly minted id.
        channel_context.on_session_minted("chat", "minted-xyz")

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=runner,
        store=store,
    )
    await reg.start()
    await adapter.deliver(
        InboundMessage(
            channel="telegram", session_key="42", text="hi", address={"chat_id": 42}
        )
    )
    await reg.stop()
    assert store.get("telegram:42:chat") == "minted-xyz"


# ----------------------------------------------------------- /new command


async def test_slash_new_clears_prefix_and_replies(store):
    adapter = FakeAdapter()
    store.set("telegram:42:chat", "old-id")
    runner_calls: list[Any] = []

    async def runner(name, cc):
        runner_calls.append(name)

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=runner,
        store=store,
    )
    await reg.start()
    await adapter.deliver(
        InboundMessage(
            channel="telegram", session_key="42", text="/new", address={"chat_id": 42}
        )
    )
    await reg.stop()
    assert runner_calls == [], "/new must NOT invoke the runner"
    assert store.get("telegram:42:chat") is None
    assert adapter.sent == [({"chat_id": 42}, "Session reset.")]


# ----------------------------------------------------------- FIFO per key


async def test_messages_on_same_key_run_sequentially(store):
    """Two quick messages on the same (channel, session_key) run in order."""
    adapter = FakeAdapter()
    order: list[str] = []

    async def slow_runner(name: str, cc):
        order.append(f"start:{cc.message}")
        await asyncio.sleep(0.05)
        order.append(f"end:{cc.message}")

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=slow_runner,
        store=store,
    )
    await reg.start()
    # Fire two messages back-to-back without awaiting between them — they
    # share the same (channel, session_key) so must run serially.
    t1 = asyncio.create_task(
        adapter.deliver(
            InboundMessage(
                channel="telegram",
                session_key="42",
                text="first",
                address={"chat_id": 42},
            )
        )
    )
    t2 = asyncio.create_task(
        adapter.deliver(
            InboundMessage(
                channel="telegram",
                session_key="42",
                text="second",
                address={"chat_id": 42},
            )
        )
    )
    await asyncio.gather(t1, t2)
    await reg.stop()
    assert order == ["start:first", "end:first", "start:second", "end:second"]


async def test_messages_on_different_keys_run_concurrently(store):
    """Different session_keys are not serialized — they overlap."""
    adapter = FakeAdapter()
    starts: list[str] = []

    async def slow_runner(name: str, cc):
        starts.append(cc.session_key)
        await asyncio.sleep(0.1)

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=slow_runner,
        store=store,
    )
    await reg.start()
    t1 = asyncio.create_task(
        adapter.deliver(
            InboundMessage(
                channel="telegram", session_key="42", text="a", address={"chat_id": 42}
            )
        )
    )
    t2 = asyncio.create_task(
        adapter.deliver(
            InboundMessage(
                channel="telegram", session_key="99", text="b", address={"chat_id": 99}
            )
        )
    )
    await asyncio.sleep(0.02)
    # Both should have started concurrently within the short delay.
    assert sorted(starts) == ["42", "99"]
    await asyncio.gather(t1, t2)
    await reg.stop()


# ----------------------------------------------------------- runner errors


async def test_runner_exception_does_not_kill_registry(store, caplog):
    adapter = FakeAdapter()

    async def boom(name, cc):
        raise RuntimeError("nope")

    reg = _make_registry(
        adapters={"telegram": adapter},
        bindings=[ChannelBinding(channel="telegram", conduit="echo")],
        conduit_lookup={"echo": _faucet_conduit()},
        runner=boom,
        store=store,
    )
    await reg.start()
    await adapter.deliver(
        InboundMessage(
            channel="telegram", session_key="42", text="hi", address={"chat_id": 42}
        )
    )
    # Second message must still be dispatched.
    await adapter.deliver(
        InboundMessage(
            channel="telegram", session_key="42", text="hi2", address={"chat_id": 42}
        )
    )
    await reg.stop()
