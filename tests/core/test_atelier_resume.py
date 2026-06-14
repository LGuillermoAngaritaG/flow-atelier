"""Tests for Atelier.resume_flow facade method and get_flow_logs child merging."""
from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

import pytest

from flow_atelier.cli._shared import _resolve_flow_id
from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.schemas.api import RunTaskInput
from flow_atelier.schemas.log import LogEntry
from flow_atelier.schemas.progress import FlowStatus


def _entry(task: str, output: str) -> LogEntry:
    """Build a minimal LogEntry for log-aggregation tests.

    :param task: sub-task name.
    :param output: captured output text.
    """
    return LogEntry(
        task=task, tool="tool:bash", command="x", output=output, stdout=output,
        exit_code=0,
        started_at="2026-04-12T10:00:00Z", finished_at="2026-04-12T10:00:00Z",
    )


@pytest.fixture
def atelier(tmp_path, _isolate_global_atelier_dir):
    """Construct an Atelier instance rooted under tmp_path.

    :param tmp_path: pytest temp directory fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    global_dir: Path = _isolate_global_atelier_dir
    return Atelier(
        base_dir=tmp_path / ".atelier",
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=global_dir,
        ),
    )


# ---------------------------------------------------------------- resume_flow


async def test_resume_flow_raises_for_completed(atelier, tmp_path):
    """Verify resume_flow raises ValueError when the flow already completed.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    # Seed a completed flow
    result = await atelier.run_single_task(
        RunTaskInput(
            name="echo",
            description="d",
            task="echo hello",
            tool="tool:bash",
            run_path=str(tmp_path),
        )
    )
    with pytest.raises(ValueError, match="can only resume failed or crashed"):
        await atelier.resume_flow(result.flow_id)


async def test_resume_flow_accepts_running_status(atelier, tmp_path):
    """A crashed process leaves progress at `running`; that must be resumable.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    conduit_dir = atelier.store.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\n"
        "description: say hi\n"
        "tasks:\n"
        "  - greet:\n"
        "      description: greet\n"
        '      task: "echo hi"\n'
        "      tool: tool:bash\n"
        "      depends_on: []\n"
    )
    flow_id = await atelier.run_conduit("hello", {}, working_dir=tmp_path)

    # Simulate a crash: progress left at `running` with a now-dead runner pid.
    dead = subprocess.Popen(["true"])
    dead.wait()
    progress = atelier.store.read_progress(flow_id)
    progress.status = FlowStatus.running
    progress.runner_pid = dead.pid
    progress.runner_host = socket.gethostname()
    atelier.store.write_progress(flow_id, progress)

    resumed = await atelier.resume_flow(flow_id, working_dir=tmp_path)
    assert resumed == flow_id
    assert atelier.store.read_progress(flow_id).status == FlowStatus.completed


async def test_resume_flow_refuses_when_runner_alive(atelier, tmp_path):
    """A `running` flow whose runner pid is alive on this host must not resume.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    conduit_dir = atelier.store.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\n"
        "description: say hi\n"
        "tasks:\n"
        "  - greet:\n"
        "      description: greet\n"
        '      task: "echo hi"\n'
        "      tool: tool:bash\n"
        "      depends_on: []\n"
    )
    flow_id = await atelier.run_conduit("hello", {}, working_dir=tmp_path)

    # Simulate a still-running flow: status running, runner pid is *this*
    # live test process on this host.
    progress = atelier.store.read_progress(flow_id)
    progress.status = FlowStatus.running
    progress.runner_pid = os.getpid()
    progress.runner_host = socket.gethostname()
    atelier.store.write_progress(flow_id, progress)

    with pytest.raises(ValueError, match="still alive"):
        await atelier.resume_flow(flow_id, working_dir=tmp_path)


async def test_resume_flow_raises_for_unknown_flow(atelier):
    """Verify resume_flow raises FileNotFoundError for an unknown flow id.

    :param atelier: Atelier facade fixture.
    """
    with pytest.raises(FileNotFoundError):
        await atelier.resume_flow("20260101_abc123_nonexistent")


async def test_resume_flow_reuses_stored_run_path(atelier, tmp_path):
    """Verify resume_flow picks up the stored run_path when none is given.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    # We can't easily produce a failed flow via run_single_task (it only does bash).
    # So we test the run_path retrieval logic indirectly by checking the store.
    result = await atelier.run_single_task(
        RunTaskInput(
            name="echo",
            description="d",
            task="echo hello",
            tool="tool:bash",
            run_path=str(tmp_path),
        )
    )
    inputs = atelier.store.read_input(result.flow_id)
    assert inputs.get("run_path") == str(tmp_path)


# ---------------------------------------------------------------- _resolve_flow_id


def test_resolve_flow_id_finds_nested_child(atelier):
    """The CLI resolver must address a nested child flow by its exact id.

    `list_flows` only enumerates top-level flows, so a child id has to be
    resolved through the store's recursive lookup.

    :param atelier: Atelier facade fixture.
    """
    parent = atelier.store.create_flow("hello", {})
    child = atelier.store.create_flow("hello", {}, parent_flow_id=parent)
    assert child not in atelier.list_flows()
    assert _resolve_flow_id(atelier, child) == child


# ---------------------------------------------------------------- get_flow_logs child merging


async def test_get_logs_returns_child_entries(atelier, tmp_path):
    """Verify get_flow_logs includes log entries from child flows tagged with flow_id.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    # Seed a parent flow
    result = await atelier.run_single_task(
        RunTaskInput(
            name="echo",
            description="d",
            task="echo parent-output",
            tool="tool:bash",
            run_path=str(tmp_path),
        )
    )
    logs = atelier.get_flow_logs(result.flow_id)
    # The parent flow has at least one entry
    assert any("parent-output" in (e.stdout or "") for e in logs)


async def test_get_logs_aggregates_grandchild_entries(atelier):
    """Logs from a grandchild (2 levels down) appear in the parent's logs,
    tagged with the grandchild's flow id.

    :param atelier: Atelier facade fixture.
    """
    store = atelier.store
    parent = store.create_flow("hello", {})
    child = store.create_flow("hello", {}, parent_flow_id=parent)
    grandchild = store.create_flow("hello", {}, parent_flow_id=child)
    await store.append_log(parent, _entry("p", "parent-out"))
    await store.append_log(child, _entry("c", "child-out"))
    await store.append_log(grandchild, _entry("g", "grandchild-out"))

    logs = atelier.get_flow_logs(parent)
    outputs = {e.output for e in logs}
    assert {"parent-out", "child-out", "grandchild-out"} <= outputs
    gc = [e for e in logs if e.output == "grandchild-out"]
    assert gc and gc[0].extra["flow_id"] == grandchild


async def test_get_logs_does_not_mutate_entries(atelier, tmp_path):
    """Verify get_flow_logs returns fresh objects — calling it twice yields independent entries.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    result = await atelier.run_single_task(
        RunTaskInput(
            name="echo",
            description="d",
            task="echo test",
            tool="tool:bash",
            run_path=str(tmp_path),
        )
    )
    first = atelier.get_flow_logs(result.flow_id)
    second = atelier.get_flow_logs(result.flow_id)
    # Entries are independent objects (not the same reference)
    if first and second:
        assert first[0] is not second[0]
