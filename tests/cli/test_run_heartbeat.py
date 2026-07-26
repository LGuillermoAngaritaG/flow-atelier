"""Heartbeat: prove the run stream shows liveness during silence."""
from __future__ import annotations

import asyncio

import pytest

from flow_atelier.cli import _shared
from flow_atelier.cli.commands import run as run_cmd
from flow_atelier.cli.rendering.render import render_heartbeat
from flow_atelier.schemas.log import TaskEvent
from flow_atelier.schemas.progress import TaskStatus


@pytest.fixture
def fast_heartbeat(monkeypatch):
    """Shrink the heartbeat intervals so tests stay sub-second.

    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setattr(run_cmd, "HEARTBEAT_SECONDS", 0.1)
    monkeypatch.setattr(run_cmd, "_HEARTBEAT_TICK_SECONDS", 0.02)


@pytest.fixture
def captured(monkeypatch):
    """Capture everything the run command prints.

    :param monkeypatch: pytest monkeypatch fixture.
    :returns: list that accumulates rendered console output.
    """
    lines: list[str] = []

    class Recorder:
        """Stand-in console recording printed renderables as text."""

        def print(self, *args) -> None:
            """Record the printed renderable.

            :param args: renderable(s) passed to the real console.
            """
            for arg in args:
                lines.append(getattr(arg, "plain", str(arg)))

    monkeypatch.setattr(run_cmd, "console", Recorder())
    return lines


class TestHeartbeat:
    async def test_beats_while_the_stream_is_silent(
        self, fast_heartbeat, captured
    ) -> None:
        """A quiet task still produces a "still working" line.

        :param fast_heartbeat: shortened heartbeat interval fixture.
        :param captured: captured console output fixture.
        """
        running = run_cmd._RunningTasks()
        running.start("build")
        _shared.mark_activity()

        async def quiet() -> str:
            """Sleep well past the heartbeat threshold without printing."""
            await asyncio.sleep(0.4)
            return "done"

        result = await run_cmd._with_heartbeat(quiet(), running)

        assert result == "done"
        beats = [line for line in captured if "still working" in line]
        assert beats, "a silent run must show liveness"
        assert "build" in beats[0], "the heartbeat should name the running task"

    async def test_silent_while_output_is_flowing(
        self, fast_heartbeat, captured
    ) -> None:
        """An actively streaming run must not be interrupted by heartbeats.

        :param fast_heartbeat: shortened heartbeat interval fixture.
        :param captured: captured console output fixture.
        """
        running = run_cmd._RunningTasks()
        running.start("build")

        async def chatty() -> str:
            """Emit activity faster than the heartbeat threshold."""
            for _ in range(20):
                _shared.mark_activity()
                await asyncio.sleep(0.02)
            return "done"

        await run_cmd._with_heartbeat(chatty(), running)

        assert [line for line in captured if "still working" in line] == []

    async def test_cancellation_propagates_and_stops_the_beat(
        self, fast_heartbeat, captured
    ) -> None:
        """`atelier stop` must still cancel cleanly through the wrapper.

        The heartbeat wraps the engine coroutine, so a regression here would
        break the SIGTERM path the stop command relies on.

        :param fast_heartbeat: shortened heartbeat interval fixture.
        :param captured: captured console output fixture.
        """
        running = run_cmd._RunningTasks()

        async def stopped() -> None:
            """Behave like an engine run killed by SIGTERM."""
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await run_cmd._with_heartbeat(stopped(), running)

        # The beat task must not outlive the run.
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        await asyncio.sleep(0.05)
        assert all(t.cancelled() or t.done() for t in pending)


class TestRunningTasks:
    def test_repeating_task_stays_tracked_until_its_last_iteration(self) -> None:
        """A looping task must not disappear from the heartbeat mid-loop."""
        running = run_cmd._RunningTasks()
        running.start("loop")

        running.finish(
            TaskEvent(
                task="loop",
                tool="tool:bash",
                status=TaskStatus.completed,
                iteration=1,
                of=3,
            )
        )
        assert "loop" in running.elapsed(), "still looping — keep showing it"

        running.finish(
            TaskEvent(
                task="loop",
                tool="tool:bash",
                status=TaskStatus.completed,
                iteration=3,
                of=3,
            )
        )
        assert running.elapsed() == {}

    def test_failed_task_stops_being_tracked(self) -> None:
        """A failed task is done regardless of its remaining iterations."""
        running = run_cmd._RunningTasks()
        running.start("loop")

        running.finish(
            TaskEvent(
                task="loop",
                tool="tool:bash",
                status=TaskStatus.failed,
                success=False,
                iteration=1,
                of=3,
            )
        )
        assert running.elapsed() == {}


class TestRenderHeartbeat:
    def test_names_every_concurrent_task(self) -> None:
        """With max_concurrency > 1 the line must account for each task."""
        text = render_heartbeat({"alpha": 65.0, "beta": 3.0}).plain
        assert "alpha 1m 05s" in text
        assert "beta 3.0s" in text

    def test_degrades_without_task_detail(self) -> None:
        """Between tasks there is nothing to name, but liveness still shows."""
        assert render_heartbeat({}).plain == "· still working"
