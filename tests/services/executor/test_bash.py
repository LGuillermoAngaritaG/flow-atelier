"""BashExecutor tests."""
import sys

import pytest

from flow_atelier.schemas.conduit import TaskDefinition, ToolType
from flow_atelier.services.executor.base import FlowContext
from flow_atelier.services.executor.bash import BashExecutor


def _task(cmd: str) -> TaskDefinition:
    """Build a bash TaskDefinition stub for tests.

    :param cmd: shell command string used as the task body.
    """
    return TaskDefinition(
        name="t",
        description="d",
        task=cmd,
        tool=ToolType.bash,
        depends_on=[],
    )


def _ctx(timeout: int = 30) -> FlowContext:
    """Build a FlowContext stub with a fake store.

    :param timeout: per-task timeout in seconds.
    """
    return FlowContext(
        flow_id="fake",
        store=None,  # type: ignore[arg-type]
        inputs={},
        timeout=timeout,
    )


async def test_echo_success():
    """Verify a simple echo command succeeds with stdout captured."""
    r = await BashExecutor().execute(_task("echo hello"), "echo hello", _ctx())
    assert r.exit_code == 0
    assert "hello" in r.output
    assert r.stderr == ""


async def test_failure_exit_code():
    """Verify non-zero exit codes propagate and success is False."""
    r = await BashExecutor().execute(_task("exit 5"), "exit 5", _ctx())
    assert r.exit_code == 5
    assert not r.success


@pytest.mark.skipif(sys.platform == "win32", reason="bash ; syntax not supported in cmd.exe")
async def test_stderr_captured():
    """Verify stderr output is captured separately from stdout."""
    r = await BashExecutor().execute(
        _task("echo boom 1>&2; exit 1"),
        "echo boom 1>&2; exit 1",
        _ctx(),
    )
    assert r.exit_code == 1
    assert "boom" in r.stderr


async def test_timeout_kills_process():
    """Verify a long-running command is killed when the timeout expires."""
    r = await BashExecutor().execute(
        _task("sleep 5"),
        "sleep 5",
        _ctx(timeout=1),
    )
    assert r.exit_code == 124
    assert "timeout" in r.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="bash ; syntax not supported in cmd.exe")
async def test_timeout_preserves_partial_output():
    """Verify output printed before the timeout survives the kill."""
    cmd = "echo hello; sleep 5"
    r = await BashExecutor().execute(_task(cmd), cmd, _ctx(timeout=1))
    assert r.exit_code == 124
    assert "hello" in r.stdout
    assert "hello" in r.output
    assert "timeout" in r.stderr
