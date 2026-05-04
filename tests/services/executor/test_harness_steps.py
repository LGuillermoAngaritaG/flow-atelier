"""Tests for intermediate step capture in _BufferingClient."""
from __future__ import annotations

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    TextContentBlock,
    ToolCallLocation,
    ToolCallProgress,
    ToolCallStart,
)

from app.schemas.log import IntermediateStep, StepKind
from app.services.executor.harness import _BufferingClient
from app.services.executor.prompt_sink import PermissionOption


class RecordingSink:
    """Minimal sink that records display_step calls."""

    def __init__(self) -> None:
        self.display_log: list[str] = []
        self.step_log: list[IntermediateStep] = []

    async def display(self, text: str) -> None:
        self.display_log.append(text)

    async def start_agent_turn(self, label: str = "agent") -> None:
        pass

    async def request_input(self, prompt: str) -> str:
        raise EOFError

    async def request_permission(
        self, summary: str, options: list[PermissionOption]
    ) -> str:
        return options[0].id

    async def display_step(self, step: IntermediateStep) -> None:
        self.step_log.append(step)


class TestBufferingClientSteps:
    async def test_thinking_chunk_captured(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = AgentThoughtChunk(
            sessionUpdate="agent_thought_chunk",
            content=TextContentBlock(type="text", text="Let me think about this"),
        )
        await client.session_update("s1", update)
        assert len(client.steps) == 1
        assert client.steps[0].kind == StepKind.thinking
        assert client.steps[0].text == "Let me think about this"

    async def test_tool_call_start_captured(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallStart(
            sessionUpdate="tool_call",
            tool_call_id="tc-1",
            title="Read file",
            kind="read",
            status="pending",
            locations=[ToolCallLocation(path="/src/main.py")],
            raw_input={"path": "/src/main.py"},
        )
        await client.session_update("s1", update)
        assert len(client.steps) == 1
        step = client.steps[0]
        assert step.kind == StepKind.tool_call
        assert step.tool_call_id == "tc-1"
        assert step.tool_name == "Read file"
        assert step.tool_kind == "read"
        assert step.tool_status == "pending"
        assert step.locations == ["/src/main.py"]

    async def test_tool_call_progress_completed_captured(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallProgress(
            sessionUpdate="tool_call_update",
            tool_call_id="tc-1",
            status="completed",
            raw_output={"content": "file contents"},
        )
        await client.session_update("s1", update)
        assert len(client.steps) == 1
        step = client.steps[0]
        assert step.kind == StepKind.tool_result
        assert step.tool_call_id == "tc-1"
        assert step.tool_status == "completed"

    async def test_tool_call_progress_failed_captured(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallProgress(
            sessionUpdate="tool_call_update",
            tool_call_id="tc-2",
            status="failed",
        )
        await client.session_update("s1", update)
        assert len(client.steps) == 1
        assert client.steps[0].tool_status == "failed"

    async def test_tool_call_progress_pending_ignored(self) -> None:
        """Only completed/failed ToolCallProgress should create a step."""
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallProgress(
            sessionUpdate="tool_call_update",
            tool_call_id="tc-1",
            status="in_progress",
        )
        await client.session_update("s1", update)
        assert len(client.steps) == 0

    async def test_stream_steps_calls_display_step(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=True)
        update = AgentThoughtChunk(
            sessionUpdate="agent_thought_chunk",
            content=TextContentBlock(type="text", text="thinking"),
        )
        await client.session_update("s1", update)
        assert len(sink.step_log) == 1
        assert sink.step_log[0].kind == StepKind.thinking

    async def test_no_stream_steps_skips_display_step(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = AgentThoughtChunk(
            sessionUpdate="agent_thought_chunk",
            content=TextContentBlock(type="text", text="thinking"),
        )
        await client.session_update("s1", update)
        # Steps captured, but not sent to sink
        assert len(client.steps) == 1
        assert len(sink.step_log) == 0

    async def test_stream_steps_without_messages_streams_all_step_kinds(
        self,
    ) -> None:
        """``stream_steps=True, stream_messages=False`` is the non-interactive
        default: tool/thinking activity surfaces live but the agent's prose
        is still buffered for the post-task panel."""
        sink = RecordingSink()
        client = _BufferingClient(
            sink, stream_messages=False, stream_steps=True
        )
        await client.session_update(
            "s1",
            AgentThoughtChunk(
                sessionUpdate="agent_thought_chunk",
                content=TextContentBlock(type="text", text="planning"),
            ),
        )
        await client.session_update(
            "s1",
            ToolCallStart(
                sessionUpdate="tool_call",
                tool_call_id="tc-1",
                title="Read",
                kind="read",
                status="pending",
            ),
        )
        await client.session_update(
            "s1",
            ToolCallProgress(
                sessionUpdate="tool_call_update",
                tool_call_id="tc-1",
                status="completed",
            ),
        )
        kinds = [s.kind for s in sink.step_log]
        assert kinds == [
            StepKind.thinking,
            StepKind.tool_call,
            StepKind.tool_result,
        ]
        assert sink.display_log == []

    async def test_stream_steps_does_not_stream_messages(self) -> None:
        """Steps streaming must not pull message chunks along with it —
        they are independent gates."""
        sink = RecordingSink()
        client = _BufferingClient(
            sink, stream_messages=False, stream_steps=True
        )
        await client.session_update(
            "s1",
            AgentMessageChunk(
                sessionUpdate="agent_message_chunk",
                content=TextContentBlock(type="text", text="hello world"),
            ),
        )
        # Buffered for the post-task panel...
        assert "".join(client.buffer) == "hello world"
        # ...but never streamed live.
        assert sink.display_log == []

    async def test_tool_input_truncated(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallStart(
            sessionUpdate="tool_call",
            tool_call_id="tc-1",
            title="Write",
            raw_input="x" * 1000,
        )
        await client.session_update("s1", update)
        assert len(client.steps[0].tool_input) <= 500

    async def test_tool_output_truncated(self) -> None:
        sink = RecordingSink()
        client = _BufferingClient(sink, stream_steps=False)
        update = ToolCallProgress(
            sessionUpdate="tool_call_update",
            tool_call_id="tc-1",
            status="completed",
            raw_output="y" * 1000,
        )
        await client.session_update("s1", update)
        assert len(client.steps[0].tool_output) <= 500
