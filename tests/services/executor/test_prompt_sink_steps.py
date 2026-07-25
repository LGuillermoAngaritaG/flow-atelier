"""Tests for PromptSink.display_step() with IntermediateStep."""
from __future__ import annotations

import io

from rich.console import Console

from flow_atelier.schemas.log import IntermediateStep, StepKind
from flow_atelier.services.executor.prompt_sink import TerminalPromptSink


def _make_sink() -> tuple[TerminalPromptSink, io.StringIO]:
    """Build a TerminalPromptSink wired to a Rich Console writing to a buffer."""
    buf = io.StringIO()
    console = Console(file=buf, soft_wrap=True, no_color=True, width=120)
    sink = TerminalPromptSink(out=buf, console=console)
    return sink, buf


class TestDisplayStep:
    async def test_thinking_step_prints_dim_text(self) -> None:
        """Verify thinking steps render with the thought-bubble glyph."""
        sink, buf = _make_sink()
        step = IntermediateStep(kind=StepKind.thinking, text="Let me analyze this code")
        await sink.display_step(step)
        output = buf.getvalue()
        assert "💭" in output
        assert "Let me analyze" in output

    async def test_tool_call_step_prints_tool_name(self) -> None:
        """Verify tool_call steps render the tool name."""
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Read",
            tool_kind="read",
            locations=["/foo/bar.py"],
        )
        await sink.display_step(step)
        output = buf.getvalue()
        assert "tool" in output.lower() or "Read" in output
        assert "Read" in output

    async def test_tool_call_step_shows_location(self) -> None:
        """Verify tool_call steps render the affected file location."""
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Edit",
            locations=["/src/main.py"],
        )
        await sink.display_step(step)
        output = buf.getvalue()
        assert "/src/main.py" in output

    async def test_successful_tool_result_is_suppressed(self) -> None:
        """A successful tool result adds no information live, so it is dropped.

        The step is still persisted and shown by ``atelier logs --show steps``;
        only the live stream skips it to halve the per-tool-call line count.
        """
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_result,
            tool_call_id="tc-1",
            tool_status="completed",
        )
        await sink.display_step(step)
        assert buf.getvalue() == ""

    async def test_tool_call_shows_command_from_payload(self) -> None:
        """A Bash call with no file locations still shows its command."""
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Bash",
            tool_input='{"command": "pytest tests/ -x", "description": "run tests"}',
        )
        await sink.display_step(step)
        assert "pytest tests/ -x" in buf.getvalue()

    async def test_tool_result_failed_prints_status(self) -> None:
        """Verify tool_result steps render the failed status."""
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_result,
            tool_call_id="tc-1",
            tool_status="failed",
        )
        await sink.display_step(step)
        output = buf.getvalue()
        assert "failed" in output

    async def test_thinking_text_truncated_for_display(self) -> None:
        """Verify long thinking text is truncated when rendered."""
        sink, buf = _make_sink()
        long_text = "x" * 300
        step = IntermediateStep(kind=StepKind.thinking, text=long_text)
        await sink.display_step(step)
        output = buf.getvalue()
        # Should not contain all 300 chars — truncated around 120
        assert len(output) < 350

    async def test_step_is_tagged_with_current_task(self) -> None:
        """Steps carry their owning task so parallel streams stay readable."""
        from flow_atelier.modules.engine import _current_task_ctx

        token = _current_task_ctx.set("research")
        try:
            sink, buf = _make_sink()
            await sink.display_step(
                IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
            )
            assert "research" in buf.getvalue()
        finally:
            _current_task_ctx.reset(token)
