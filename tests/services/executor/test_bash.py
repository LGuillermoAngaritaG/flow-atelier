"""BashExecutor tests."""
import pytest

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import FlowContext
from app.services.executor.bash import BashExecutor


def _task(cmd: str) -> TaskDefinition:
    return TaskDefinition(
        name="t",
        description="d",
        task=cmd,
        tool=ToolType.bash,
        depends_on=[],
    )


def _ctx(timeout: int = 30) -> FlowContext:
    return FlowContext(
        flow_id="fake",
        store=None,  # type: ignore[arg-type]
        inputs={},
        timeout=timeout,
    )


async def test_echo_success():
    r = await BashExecutor().execute(_task("echo hello"), "echo hello", _ctx())
    assert r.exit_code == 0
    assert "hello" in r.output
    assert r.stderr == ""


async def test_failure_exit_code():
    r = await BashExecutor().execute(_task("exit 5"), "exit 5", _ctx())
    assert r.exit_code == 5
    assert not r.success


async def test_stderr_captured():
    r = await BashExecutor().execute(
        _task("echo boom 1>&2; exit 1"),
        "echo boom 1>&2; exit 1",
        _ctx(),
    )
    assert r.exit_code == 1
    assert "boom" in r.stderr


async def test_timeout_kills_process():
    r = await BashExecutor().execute(
        _task("sleep 5"),
        "sleep 5",
        _ctx(timeout=1),
    )
    assert r.exit_code == 124
    assert "timeout" in r.stderr
