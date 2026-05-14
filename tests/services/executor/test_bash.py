"""BashExecutor tests."""

from pathlib import Path

from app.schemas.conduit import TaskDefinition, ToolType
from app.services.executor.base import FlowContext
from app.services.executor.bash import BashExecutor


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


def _ctx(timeout: int = 30, working_dir: Path | None = None) -> FlowContext:
    """Build a FlowContext stub with a fake store.

    :param timeout: per-task timeout in seconds.
    :param working_dir: optional working directory for the subprocess.
    """
    return FlowContext(
        flow_id="fake",
        store=None,  # type: ignore[arg-type]
        inputs={},
        timeout=timeout,
        working_dir=working_dir,
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


async def test_working_dir_sets_subprocess_cwd(tmp_path):
    """Verify BashExecutor runs the command in context.working_dir."""
    marker = tmp_path / "cwd_marker.txt"
    r = await BashExecutor().execute(
        _task(f"pwd > {marker}"),
        f"pwd > {marker}",
        _ctx(working_dir=tmp_path),
    )
    assert r.exit_code == 0
    assert tmp_path.name in marker.read_text().strip()
