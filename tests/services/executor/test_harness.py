"""HarnessExecutor unit tests using the fake ACP agent fixture."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import FlowContext
from app.services.executor.harness import (
    DEFAULT_DONE_MARKER,
    AcpHarnessExecutor,
    ClaudeHarness,
    build_interactive_suffix,
)
from app.services.executor.prompt_sink import PermissionOption


FAKE_AGENT = Path(__file__).resolve().parents[2] / "fixtures" / "fake_acp_agent.py"


def _fake_cmd(script: dict[str, Any]) -> list[str]:
    return [sys.executable, str(FAKE_AGENT), "--script", json.dumps(script)]


def _task(prompt: str, *, interactive: bool = False) -> TaskDefinition:
    return TaskDefinition(
        name="h",
        description="d",
        task=prompt,
        tool=ToolType.claude,
        depends_on=[],
        interactive=interactive,
    )


def _ctx(timeout: int = 30) -> FlowContext:
    return FlowContext(
        flow_id="fake", store=None, inputs={}, timeout=timeout  # type: ignore[arg-type]
    )


class RecordingSink:
    """PromptSink double for tests."""

    def __init__(
        self,
        replies: list[str] | None = None,
        perm_choice: str | None = None,
    ) -> None:
        self.display_log: list[str] = []
        self.input_prompts: list[str] = []
        self.agent_turn_starts: list[str] = []
        self._replies = list(replies or [])
        self.perm_log: list[str] = []
        self._perm_choice = perm_choice

    async def display(self, text: str) -> None:
        self.display_log.append(text)

    async def start_agent_turn(self, label: str = "agent") -> None:
        self.agent_turn_starts.append(label)

    async def request_input(self, prompt: str) -> str:
        self.input_prompts.append(prompt)
        if not self._replies:
            raise EOFError("no more scripted replies")
        return self._replies.pop(0)

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        self.perm_log.append(summary)
        if self._perm_choice is not None:
            return self._perm_choice
        return options[0].id


class TestNonInteractive:
    async def test_single_turn_success(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {"turns": [{"chunks": ["answer: ok"], "stop": "end_turn"}]}
            ),
            sink=sink,
        )
        result = await executor.execute(_task("hello"), "hello", _ctx())
        assert result.exit_code == 0
        assert "answer: ok" in result.output

    async def test_chunks_concatenated(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {
                            "chunks": ["hello ", "from ", "agent"],
                            "stop": "end_turn",
                        }
                    ]
                }
            ),
            sink=sink,
        )
        result = await executor.execute(_task("x"), "x", _ctx())
        assert result.exit_code == 0
        assert "hello from agent" in result.output

    async def test_refusal_marks_failure(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {"turns": [{"chunks": ["cannot"], "stop": "refusal"}]}
            ),
            sink=sink,
        )
        result = await executor.execute(_task("x"), "x", _ctx())
        assert result.exit_code != 0
        assert "refusal" in result.stderr

    async def test_timeout(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {"delay_before": 5, "chunks": ["late"], "stop": "end_turn"}
                    ]
                }
            ),
            sink=sink,
        )
        result = await executor.execute(_task("slow"), "slow", _ctx(timeout=2))
        assert result.exit_code == 124
        assert "timeout" in result.stderr.lower()

    async def test_non_interactive_does_not_stream_to_sink(self) -> None:
        """Non-interactive harness tasks must not double-render: chunks
        are captured into the result but NOT mirrored to the sink (the
        engine renders a final panel from result.output afterwards)."""
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {"turns": [{"chunks": ["A", "B"], "stop": "end_turn"}]}
            ),
            sink=sink,
        )
        result = await executor.execute(_task("x"), "x", _ctx())
        assert "AB" in result.output
        assert sink.display_log == []


class TestInteractiveStreaming:
    async def test_interactive_streams_chunks_to_sink(self) -> None:
        """Interactive mode keeps a live stream so the user can follow
        the agent while deciding their next reply."""
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {
                            "chunks": ["A", "B", "[ATELIER_DONE]"],
                            "stop": "end_turn",
                        }
                    ]
                }
            ),
            sink=sink,
        )
        await executor.execute(_task("x", interactive=True), "x", _ctx())
        assert "A" in "".join(sink.display_log)
        assert "B" in "".join(sink.display_log)


class TestInteractive:
    async def test_interactive_calls_start_agent_turn_per_turn(self) -> None:
        """The interactive loop must signal each agent turn to the sink so
        the terminal UI can bracket it with a styled rule."""
        sink = RecordingSink(replies=["my answer"])
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {"chunks": ["asking?"], "stop": "end_turn"},
                        {"chunks": ["thanks [ATELIER_DONE]"], "stop": "end_turn"},
                    ]
                }
            ),
            sink=sink,
        )
        await executor.execute(
            _task("go", interactive=True), "go", _ctx()
        )
        # Two agent turns ⇒ two calls.
        assert len(sink.agent_turn_starts) == 2

    async def test_marker_hidden_from_live_stream(self) -> None:
        """The done marker must not be displayed to the user even in
        interactive mode (live stream path)."""
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {
                            "chunks": ["here is the answer ", "[ATELIER_DONE]"],
                            "stop": "end_turn",
                        }
                    ]
                }
            ),
            sink=sink,
        )
        await executor.execute(
            _task("x", interactive=True), "x", _ctx()
        )
        displayed = "".join(sink.display_log)
        assert "here is the answer" in displayed
        assert "[ATELIER_DONE]" not in displayed

    async def test_marker_first_turn_terminates(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {
                            "chunks": ["doing work ", "[ATELIER_DONE]"],
                            "stop": "end_turn",
                        }
                    ]
                }
            ),
            sink=sink,
        )
        result = await executor.execute(
            _task("do it", interactive=True), "do it", _ctx()
        )
        assert result.exit_code == 0
        # The done marker is an internal protocol sentinel — it must NOT
        # be returned to callers as user-visible content (would otherwise
        # also persist into logs.json).
        assert "[ATELIER_DONE]" not in result.output
        assert "doing work" in result.output
        assert sink.input_prompts == []

    async def test_multi_turn_with_user_reply(self) -> None:
        sink = RecordingSink(replies=["luis"])
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {"chunks": ["what is your name?"], "stop": "end_turn"},
                        {
                            "chunks": ["hello luis [ATELIER_DONE]"],
                            "stop": "end_turn",
                        },
                    ]
                }
            ),
            sink=sink,
        )
        result = await executor.execute(
            _task("greet me", interactive=True), "greet me", _ctx()
        )
        assert result.exit_code == 0
        assert "what is your name?" in result.output
        assert "hello luis" in result.output
        # Marker stripped from the user-visible result.
        assert "[ATELIER_DONE]" not in result.output
        assert len(sink.input_prompts) == 1

    async def test_missing_marker_fails_when_sink_exhausted(self) -> None:
        sink = RecordingSink(replies=[])
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {"turns": [{"chunks": ["ready"], "stop": "end_turn"}]}
            ),
            sink=sink,
        )
        result = await executor.execute(
            _task("go", interactive=True), "go", _ctx()
        )
        assert result.exit_code != 0
        assert "[ATELIER_DONE]" not in result.output

    async def test_custom_marker(self) -> None:
        sink = RecordingSink()
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {"turns": [{"chunks": ["done <<FIN>>"], "stop": "end_turn"}]}
            ),
            sink=sink,
            done_marker="<<FIN>>",
        )
        result = await executor.execute(
            _task("x", interactive=True), "x", _ctx()
        )
        assert result.exit_code == 0
        # Custom markers are stripped just like the default.
        assert "<<FIN>>" not in result.output
        assert "done" in result.output

    async def test_permission_routed_to_sink(self) -> None:
        sink = RecordingSink(perm_choice="allow")
        executor = AcpHarnessExecutor(
            launch_cmd=_fake_cmd(
                {
                    "turns": [
                        {
                            "ask_permission": {
                                "summary": "run rm?",
                                "options": [
                                    {"id": "allow", "label": "Allow"},
                                    {"id": "deny", "label": "Deny"},
                                ],
                            },
                            "chunks": [" [ATELIER_DONE]"],
                            "stop": "end_turn",
                        }
                    ]
                }
            ),
            sink=sink,
        )
        result = await executor.execute(
            _task("x", interactive=True), "x", _ctx()
        )
        assert result.exit_code == 0
        assert sink.perm_log == ["run rm?"]
        assert "[perm:allow]" in result.output


class TestPreset:
    def test_claude_harness_default_launch_cmd(self) -> None:
        h = ClaudeHarness(sink=RecordingSink())
        assert "claude-code-acp" in " ".join(h.launch_cmd)

    def test_claude_harness_override_launch_cmd(self) -> None:
        h = ClaudeHarness(sink=RecordingSink(), launch_cmd=["foo", "bar"])
        assert h.launch_cmd == ["foo", "bar"]


def test_default_marker_constant() -> None:
    assert DEFAULT_DONE_MARKER == "[ATELIER_DONE]"


def test_interactive_suffix_contains_marker() -> None:
    suffix = build_interactive_suffix("[ATELIER_DONE]")
    assert "[ATELIER_DONE]" in suffix
    assert "do not" in suffix.lower() or "not echo" in suffix.lower()
