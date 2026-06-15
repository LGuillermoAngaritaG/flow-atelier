"""Unit tests for read-side flow liveness reclassification."""
import os
import socket
import subprocess
import sys

from flow_atelier.modules.liveness import (
    StopDecision,
    display_status,
    is_crashed,
    stop_decision,
)
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


def _running_here(pid: int, stoppable: bool = True) -> Progress:
    """A running flow on this host with the given runner pid.

    Defaults to ``stoppable=True`` (a foreground ``atelier run`` that installed
    a graceful-stop handler); pass ``stoppable=False`` for the daemon/serve case.
    """
    return Progress(
        status=FlowStatus.running,
        runner_pid=pid,
        runner_host=socket.gethostname(),
        stoppable=stoppable,
    )


def test_stop_decision_happy_path():
    """A running flow with a live local pid and no co-tenants is stoppable."""
    p = _running_here(os.getpid())
    assert stop_decision(p, []) is StopDecision.stoppable


def test_stop_decision_already_terminal():
    """A completed/failed/stopped flow is not running, so refuse."""
    for status in (FlowStatus.completed, FlowStatus.failed, FlowStatus.stopped):
        p = Progress(status=status, runner_pid=os.getpid(), runner_host=socket.gethostname())
        assert stop_decision(p, []) is StopDecision.not_running


def test_stop_decision_crashed_pid():
    """A running flow whose local pid is provably dead is crashed, not stoppable."""
    p = _running_here(_dead_local_pid())
    assert stop_decision(p, []) is StopDecision.crashed


def test_stop_decision_foreign_host():
    """A running flow on another host cannot be stopped from here."""
    p = Progress(
        status=FlowStatus.running,
        runner_pid=os.getpid(),
        runner_host="some-other-box-that-is-not-us",
    )
    assert stop_decision(p, []) is StopDecision.foreign_host


def test_stop_decision_no_pid():
    """A running flow with no recorded pid cannot be stopped."""
    p = Progress(status=FlowStatus.running, runner_host=socket.gethostname())
    assert stop_decision(p, []) is StopDecision.no_pid


def test_stop_decision_shared_runner():
    """Two running flows sharing one pid+host refuse (the scheduler case)."""
    target = _running_here(os.getpid())
    sibling = _running_here(os.getpid())
    assert stop_decision(target, [sibling]) is StopDecision.shared_runner


def test_stop_decision_other_flow_different_pid_is_stoppable():
    """A co-existing flow on a different pid does not block a stop."""
    target = _running_here(os.getpid())
    other = _running_here(_dead_local_pid())
    assert stop_decision(target, [other]) is StopDecision.stoppable


def test_stop_decision_not_stoppable_no_co_tenant():
    """A live flow that installed no stop handler refuses even when alone.

    This is the scheduler-daemon case: signalling its pid would tear down the
    whole daemon, so it must refuse regardless of whether a co-tenant exists.
    """
    p = _running_here(os.getpid(), stoppable=False)
    assert stop_decision(p, []) is StopDecision.not_stoppable


def test_stop_decision_not_stoppable_with_co_tenant():
    """A non-stoppable flow refuses even when a co-tenant shares its pid."""
    target = _running_here(os.getpid(), stoppable=False)
    sibling = _running_here(os.getpid(), stoppable=False)
    assert stop_decision(target, [sibling]) is StopDecision.not_stoppable
