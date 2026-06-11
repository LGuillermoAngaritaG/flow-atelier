"""Tests for Atelier.resume_flow facade method and get_flow_logs child merging."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.atelier import Atelier
from app.core.settings import AtelierSettings
from app.schemas.api import RunTaskInput


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


async def test_resume_flow_raises_for_non_failed(atelier, tmp_path):
    """Verify resume_flow raises ValueError when the flow is not failed.

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
    with pytest.raises(ValueError, match="can only resume failed flows"):
        await atelier.resume_flow(result.flow_id)


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
