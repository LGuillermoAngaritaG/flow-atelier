"""Integration test for the SIGTERM graceful-stop path in the engine."""
import asyncio
import os
import signal
import sys

import pytest

from flow_atelier.modules.engine import Engine
from flow_atelier.schemas.conduit import Conduit
from flow_atelier.schemas.log import ExecutionResult
from flow_atelier.schemas.progress import FlowStatus, TaskStatus
from flow_atelier.services.executor.base import ExecutorBase
from flow_atelier.services.store.filesystem import FilesystemStore


class SlowExecutor(ExecutorBase):
    """Executor whose single task sleeps long enough to be interrupted."""

    async def execute(self, task, resolved_command, context):
        await asyncio.sleep(30.0)
        return ExecutionResult(exit_code=0, output="done", stdout="done")


@pytest.fixture
def store(tmp_path):
    return FilesystemStore(tmp_path / ".atelier")


def _slow_conduit() -> Conduit:
    return Conduit.model_validate(
        {
            "name": "test",
            "description": "d",
            "tasks": [{"slow": {"description": "d", "task": "x", "tool": "tool:bash"}}],
        }
    )


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM semantics differ on Windows")
async def test_sigterm_stops_running_flow(store):
    """SIGTERM to a stoppable run finalizes the flow as ``stopped``."""
    engine = Engine({"tool:bash": SlowExecutor()}, store)
    captured: dict[str, str] = {}

    def _started(fid: str) -> None:
        captured["id"] = fid

    run_task = asyncio.create_task(
        engine.run(_slow_conduit(), {}, on_flow_started=_started, stoppable=True)
    )
    # Let the flow start and its slow task reach the running state.
    for _ in range(50):
        await asyncio.sleep(0.05)
        if captured.get("id"):
            p = store.read_progress(captured["id"])
            if p.tasks["slow"].status == TaskStatus.running:
                break

    os.kill(os.getpid(), signal.SIGTERM)

    with pytest.raises(asyncio.CancelledError):
        await run_task

    progress = store.read_progress(captured["id"])
    assert progress.status == FlowStatus.stopped
    assert progress.current_tasks == []
    assert progress.finished_at is not None
    assert progress.tasks["slow"].status == TaskStatus.cancelled


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM semantics differ on Windows")
async def test_sigterm_without_stoppable_does_not_install_handler(store):
    """A non-stoppable run leaves SIGTERM to the loop's default (no handler)."""
    loop = asyncio.get_running_loop()
    sentinel = {"fired": False}
    loop.add_signal_handler(signal.SIGTERM, lambda: sentinel.__setitem__("fired", True))
    try:
        engine = Engine({"tool:bash": SlowExecutor()}, store)
        captured: dict[str, str] = {}
        run_task = asyncio.create_task(
            engine.run(
                _slow_conduit(),
                {},
                on_flow_started=lambda fid: captured.__setitem__("id", fid),
                stoppable=False,
            )
        )
        await asyncio.sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.1)
        # Our pre-installed handler must still be the one that fired, proving
        # the engine did not hijack SIGTERM for a non-stoppable run.
        assert sentinel["fired"] is True
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
