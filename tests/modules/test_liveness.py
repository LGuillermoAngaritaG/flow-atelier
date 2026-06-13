"""Unit tests for read-side flow liveness reclassification."""
import os
import socket
import subprocess
import sys

from flow_atelier.modules.liveness import display_status, is_crashed
from flow_atelier.schemas.progress import FlowStatus, Progress


def _dead_local_pid() -> int:
    """Return a pid that has provably exited on this host.

    Spawns a trivial child, waits for it to be reaped, and returns its pid.
    On POSIX a reaped pid no longer refers to a live process, so
    ``os.kill(pid, 0)`` raises ``ProcessLookupError``.
    """
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


def test_dead_local_runner_is_crashed():
    """A running flow with a dead local pid is reclassified crashed."""
    p = Progress(
        status=FlowStatus.running,
        runner_pid=_dead_local_pid(),
        runner_host=socket.gethostname(),
    )
    assert is_crashed(p) is True
    assert display_status(p) == "crashed"


def test_live_local_runner_stays_running():
    """A running flow whose pid is alive (this process) stays running."""
    p = Progress(
        status=FlowStatus.running,
        runner_pid=os.getpid(),
        runner_host=socket.gethostname(),
    )
    assert is_crashed(p) is False
    assert display_status(p) == "running"


def test_foreign_host_stays_running():
    """A running flow on another host is never probed and stays running."""
    p = Progress(
        status=FlowStatus.running,
        runner_pid=_dead_local_pid(),
        runner_host="some-other-box-that-is-not-us",
    )
    assert is_crashed(p) is False
    assert display_status(p) == "running"


def test_legacy_progress_without_pid_stays_running():
    """A legacy progress.json with no runner_pid stays running."""
    p = Progress(status=FlowStatus.running)
    assert p.runner_pid is None
    assert is_crashed(p) is False
    assert display_status(p) == "running"


def test_terminal_status_with_dead_pid_not_crashed():
    """A completed/failed flow is never reclassified, even with a dead pid."""
    host = socket.gethostname()
    dead = _dead_local_pid()
    for status in (FlowStatus.completed, FlowStatus.failed):
        p = Progress(status=status, runner_pid=dead, runner_host=host)
        assert is_crashed(p) is False
        assert display_status(p) == status.value


def test_runner_fields_round_trip():
    """runner_pid/runner_host survive model_dump/model_validate."""
    p = Progress(
        status=FlowStatus.running, runner_pid=4242, runner_host="boxy"
    )
    dumped = p.model_dump(mode="json")
    assert dumped["runner_pid"] == 4242
    assert dumped["runner_host"] == "boxy"
    restored = Progress.model_validate(dumped)
    assert restored.runner_pid == 4242
    assert restored.runner_host == "boxy"


def test_legacy_progress_json_without_runner_fields_loads():
    """A progress dict missing the runner fields loads with both None."""
    restored = Progress.model_validate({"status": "running"})
    assert restored.runner_pid is None
    assert restored.runner_host is None
