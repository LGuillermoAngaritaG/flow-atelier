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


class TestFullMessages:
    async def test_long_message_is_not_truncated(self) -> None:
        """Agent messages render whole — this stream is machine-readable.

        Tool calls collapse because which tool ran is cheap to summarize.
        What the agent said is the payload and must survive intact.
        """
        sink, buf = _make_sink()
        body = " ".join(f"word{i}" for i in range(400))
        await sink.display_message(body)
        output = buf.getvalue()

        assert "…" not in output
        assert "word0" in output
        assert "word399" in output

    async def test_multiline_message_keeps_every_line(self) -> None:
        """Structured answers (lists, code) must not lose their shape.

        :returns: nothing.
        """
        sink, buf = _make_sink()
        await sink.display_message("Summary:\n- fixed A\n- fixed B\n- shipped C")
        output = buf.getvalue()

        for fragment in ("Summary:", "fixed A", "fixed B", "shipped C"):
            assert fragment in output

    async def test_indentation_survives_verbatim(self) -> None:
        """Continuation lines must not be re-indented to the tag column.

        Padding them looks tidier but rewrites the content: a four-space
        code block becomes a nine-space one, and what is on screen is what
        a reader copies out. `live_streamed` suppresses the result panel
        that would otherwise hold the pristine copy, so this rendering is
        the only one the terminal ever sees.
        """
        sink, buf = _make_sink()
        await sink.display_message("Here:\n    def f():\n        return 1")
        output = buf.getvalue()

        assert "\n    def f():\n" in output
        assert "\n        return 1" in output

    async def test_interior_blank_lines_survive(self) -> None:
        """Blank lines separating prose from code must reach the terminal.

        Chunks flush on a newline, so the separator rides at the end of a
        block; stripping each block deleted it.
        """
        sink, buf = _make_sink()
        await sink.display_message("Here is the fix:\n\n")
        await sink.display_message("def f():\n    return 1\n")
        output = buf.getvalue()

        assert "Here is the fix:\n\n" in output
        assert "\n    return 1" in output


class TestConcurrentTaskAttribution:
    async def test_bursts_are_tracked_per_task(self) -> None:
        """Parallel tasks must not pool their tool calls into one tally.

        One sink is shared by every executor and `max_concurrency` defaults
        to 3, so a single shared counter billed every concurrent task's
        calls to whichever task happened to flush first — the exact
        attribution this rendering exists to provide.
        """
        import asyncio

        from flow_atelier.modules.engine import _current_task_ctx

        sink, buf = _make_sink()

        def _call(name: str) -> IntermediateStep:
            """Build a pending tool-call step for ``name``.

            :param name: tool name to record.
            :returns: the step.
            """
            return IntermediateStep(
                kind=StepKind.tool_call, tool_name=name, tool_status="pending"
            )

        async def _run(task: str, tools: list[str]) -> None:
            """Emit ``tools`` as one task's burst, then close it out.

            :param task: owning task name.
            :param tools: tool names to emit in order.
            """
            _current_task_ctx.set(task)
            for name in tools:
                await sink.display_step(_call(name))
                await asyncio.sleep(0)
            await sink.flush_steps()

        await asyncio.gather(
            _run("build", ["Bash", "Read"]),
            _run("deploy", ["Grep", "Write"]),
        )
        output = buf.getvalue()

        assert "build     used 2 tools (Bash, Read)" in output
        assert "deploy    used 2 tools (Grep, Write)" in output
        # Each task announces its own burst rather than riding on a peer's.
        assert output.count("using tools") == 2
        for line in output.splitlines():
            if "deploy" in line:
                assert "Bash" not in line and "Read" not in line

    async def test_one_task_turn_boundary_leaves_a_peer_burst_open(self) -> None:
        """`flush_steps` closes only the calling task's burst.

        The harness driver calls it per task after every prompt round; it
        must not close out — or take credit for — a peer's in-flight calls.
        """
        from flow_atelier.modules.engine import _current_task_ctx

        sink, buf = _make_sink()
        _current_task_ctx.set("slow")
        await sink.display_step(
            IntermediateStep(
                kind=StepKind.tool_call, tool_name="Bash", tool_status="pending"
            )
        )
        _current_task_ctx.set("fast")
        await sink.flush_steps()

        assert "used" not in buf.getvalue(), "peer's burst was closed by another task"

        _current_task_ctx.set("slow")
        await sink.flush_steps()
        assert "slow    used 1 tool (Bash)" in buf.getvalue()
