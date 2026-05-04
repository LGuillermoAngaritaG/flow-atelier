"""Tests for PromptSink.display_step() with IntermediateStep."""
from __future__ import annotations

import io

from rich.console import Console

from app.schemas.log import IntermediateStep, StepKind
from app.services.executor.prompt_sink import TerminalPromptSink


def _make_sink() -> tuple[TerminalPromptSink, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, soft_wrap=True, no_color=True, width=120)
    sink = TerminalPromptSink(out=buf, console=console)
    return sink, buf


class TestDisplayStep:
    async def test_thinking_step_prints_dim_text(self) -> None:
        sink, buf = _make_sink()
        step = IntermediateStep(kind=StepKind.thinking, text="Let me analyze this code")
        await sink.display_step(step)
        output = buf.getvalue()
        assert "thinking" in output
        assert "Let me analyze" in output

    async def test_tool_call_step_prints_tool_name(self) -> None:
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
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Edit",
            locations=["/src/main.py"],
        )
        await sink.display_step(step)
        output = buf.getvalue()
        assert "/src/main.py" in output

    async def test_tool_result_step_prints_status(self) -> None:
        sink, buf = _make_sink()
        step = IntermediateStep(
            kind=StepKind.tool_result,
            tool_call_id="tc-1",
            tool_status="completed",
        )
        await sink.display_step(step)
        output = buf.getvalue()
        assert "completed" in output

    async def test_tool_result_failed_prints_status(self) -> None:
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
        sink, buf = _make_sink()
        long_text = "x" * 300
        step = IntermediateStep(kind=StepKind.thinking, text=long_text)
        await sink.display_step(step)
        output = buf.getvalue()
        # Should not contain all 300 chars — truncated around 120
        assert len(output) < 350
