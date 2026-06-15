"""CLI tests for `atelier stop` refusal and success reporting."""
from __future__ import annotations

import io
import os
import signal
import socket

import pytest
from rich.console import Console
from typer.testing import CliRunner

from flow_atelier.cli import app
from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.progress import FlowStatus, Progress


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolated cwd with an empty `.atelier` tree and isolated global dir."""
    (tmp_path / ".atelier" / "conduits").mkdir(parents=True)
    global_dir = tmp_path / "global"
    (global_dir / "conduits").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(global_dir))
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")
    return tmp_path


def _seed_flow(stoppable: bool, status: FlowStatus = FlowStatus.running) -> str:
    """Create a flow on disk with a live local runner and the given fields."""
    atelier = Atelier()
    flow_id = atelier.store.create_flow("report", {})
    atelier.store.write_progress(
        flow_id,
        Progress(
            status=status,
            runner_pid=os.getpid(),
            runner_host=socket.gethostname(),
            stoppable=stoppable,
        ),
    )
    return flow_id


def test_stop_refuses_non_stoppable_flow(workdir, monkeypatch):
    """A daemon/serve flow (stoppable=False) is refused and never signalled."""
    signals: list = []
    real_kill = os.kill
    monkeypatch.setattr(
        "flow_atelier.cli.commands.stop.os.kill",
        lambda pid, sig: signals.append(sig) or real_kill(pid, sig),
    )
    flow_id = _seed_flow(stoppable=False)
    result = CliRunner().invoke(app, ["stop", flow_id])
    assert result.exit_code == 1
    assert "cannot stop" in result.stdout
    assert "scheduler/server" in result.stdout
    # Only liveness probes (signal 0) may run; no real SIGTERM is sent.
    assert signal.SIGTERM not in signals


def _capture_console(monkeypatch) -> io.StringIO:
    """Replace the stop command's console with a colour-forcing capture sink."""
    buf = io.StringIO()
    monkeypatch.setattr(
        "flow_atelier.cli.commands.stop.console",
        Console(force_terminal=True, no_color=False, file=buf, width=200),
    )
    return buf


def test_stop_reports_failed_flow_in_yellow_not_green(workdir, monkeypatch):
    """When the signalled flow ends `failed`, the result is not printed green."""
    flow_id = _seed_flow(stoppable=True)

    def _fake_kill(pid, sig):
        Atelier().store.write_progress(
            flow_id,
            Progress(status=FlowStatus.failed, stoppable=True),
        )

    monkeypatch.setattr("flow_atelier.cli.commands.stop.os.kill", _fake_kill)
    buf = _capture_console(monkeypatch)

    result = CliRunner().invoke(app, ["stop", flow_id])
    assert result.exit_code == 0
    out = buf.getvalue()
    assert "failed" in out
    # Yellow ANSI (33) present, green ANSI (32) absent on the final status line.
    assert "\x1b[33m" in out
    assert "\x1b[32m" not in out


def test_stop_reports_stopped_flow_in_green(workdir, monkeypatch):
    """When the signalled flow ends `stopped`, the result is printed green."""
    flow_id = _seed_flow(stoppable=True)

    def _fake_kill(pid, sig):
        Atelier().store.write_progress(
            flow_id,
            Progress(status=FlowStatus.stopped, stoppable=True),
        )

    monkeypatch.setattr("flow_atelier.cli.commands.stop.os.kill", _fake_kill)
    buf = _capture_console(monkeypatch)

    result = CliRunner().invoke(app, ["stop", flow_id])
    assert result.exit_code == 0
    out = buf.getvalue()
    assert "stopped" in out
    assert "\x1b[32m" in out
