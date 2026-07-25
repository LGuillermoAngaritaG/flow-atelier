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

    async def test_tool_calls_collapse_into_a_burst(self) -> None:
        """A run of tool calls shows one marker and one tally, not N lines.

        A harness that makes many calls in a row would otherwise push the
        agent's reasoning and messages off screen entirely.
        """
        sink, buf = _make_sink()
        for name in ("Bash", "Read", "Read", "Grep"):
            await sink.display_step(
                IntermediateStep(kind=StepKind.tool_call, tool_name=name)
            )
        await sink.flush_steps()
        output = buf.getvalue()

        assert "using tools" in output
        assert "used 4 tools" in output
        # Names survive in the tally; per-call arguments do not.
        assert "Read 2" in output
        assert "Bash" in output
        assert len([ln for ln in output.splitlines() if ln.strip()]) == 2

    async def test_burst_is_closed_by_the_next_non_tool_step(self) -> None:
        """Thinking after a burst forces the tally out before it renders."""
        sink, buf = _make_sink()
        await sink.display_step(
            IntermediateStep(kind=StepKind.tool_call, tool_name="Bash")
        )
        await sink.display_step(
            IntermediateStep(kind=StepKind.thinking, text="now I can summarize")
        )
        output = buf.getvalue()

        assert output.index("used 1 tool") < output.index("now I can summarize")

    async def test_failed_tool_result_still_surfaces(self) -> None:
        """Failures must not be swallowed by the burst collapsing."""
        sink, buf = _make_sink()
        await sink.display_step(
            IntermediateStep(kind=StepKind.tool_call, tool_name="Bash")
        )
        await sink.display_step(
            IntermediateStep(
                kind=StepKind.tool_result,
                tool_status="failed",
                tool_output="exit 1",
            )
        )
        output = buf.getvalue()

        assert "failed" in output
        assert "exit 1" in output

    async def test_agent_message_is_previewed(self) -> None:
        """Non-interactive runs surface what the agent said between tools."""
        sink, buf = _make_sink()
        await sink.display_message("Grouped the commits into three sections.")
        assert "Grouped the commits into three sections." in buf.getvalue()

    async def test_message_closes_an_open_burst(self) -> None:
        """The tally lands before the message that follows it."""
        sink, buf = _make_sink()
        await sink.display_step(
            IntermediateStep(kind=StepKind.tool_call, tool_name="Read")
        )
        await sink.display_message("Done reading.")
        output = buf.getvalue()

        assert output.index("used 1 tool") < output.index("Done reading.")

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

    async def test_tool_arguments_remain_available_post_hoc(self) -> None:
        """The live view drops per-call arguments; the log view keeps them.

        Collapsing the live stream must not lose the detail — it moves it to
        ``atelier logs --show steps``, which renders via ``_render_step``.
        """
        from flow_atelier.cli.rendering.render import _render_step

        step = IntermediateStep(
            kind=StepKind.tool_call,
            tool_name="Bash",
            tool_input='{"command": "pytest tests/ -x", "description": "run tests"}',
        )
        assert "pytest tests/ -x" in _render_step(step).plain

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
