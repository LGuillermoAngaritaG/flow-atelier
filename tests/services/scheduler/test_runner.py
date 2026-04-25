"""SchedulerDaemon: sync, fire, and one-shot fired-state tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.schemas.schedule import ScheduleDefinition
from app.services.scheduler.runner import SchedulerDaemon, _RELOAD_JOB_ID
from app.services.scheduler.store import ScheduleStore


UTC = ZoneInfo("UTC")


RECURRING_FAR_FUTURE = """
conduit: report
schedule:
  type: recurring
  days: [mon]
  hours: ["09:00"]
"""

ONCE_FAR_FUTURE = """
conduit: backfill
schedule:
  type: once
  at: "2099-05-01T09:00:00"
"""

ONCE_OTHER_TIME = """
conduit: backfill
schedule:
  type: once
  at: "2099-06-01T09:00:00"
"""


def _write(store: ScheduleStore, name: str, body: str) -> Path:
    path = store.path_for(name)
    path.write_text(body)
    return path


@pytest.fixture
def store(tmp_path) -> ScheduleStore:
    return ScheduleStore(tmp_path / "schedules")


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[ScheduleDefinition, Path]] = []
        self.raise_on_next = False

    async def __call__(
        self, definition: ScheduleDefinition, working_dir: Path
    ) -> None:
        self.calls.append((definition, working_dir))
        if self.raise_on_next:
            self.raise_on_next = False
            raise RuntimeError("forced failure for test")


@pytest.fixture
def executor() -> _RecordingExecutor:
    return _RecordingExecutor()


@pytest.fixture
async def daemon(tmp_path, store, executor):
    d = SchedulerDaemon(
        store,
        executor=executor,
        default_zone=UTC,
        default_working_dir=tmp_path,
        reload_interval_seconds=3600,  # never auto-reloads during tests
    )
    yield d
    await d.stop()


# -------------------------------------------------------------- start / stop


async def test_start_registers_existing_schedules(daemon, store):
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    _write(store, "once", ONCE_FAR_FUTURE)
    await daemon.start()
    planned = {p.name for p in daemon.list_planned()}
    assert planned == {"weekly", "once"}


async def test_start_is_idempotent(daemon, store):
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon.start()
    await daemon.start()
    assert {p.name for p in daemon.list_planned()} == {"weekly"}


async def test_start_with_no_schedules(daemon):
    await daemon.start()
    assert daemon.list_planned() == []


async def test_load_errors_are_surfaced_not_fatal(daemon, store):
    _write(store, "good", RECURRING_FAR_FUTURE)
    _write(store, "broken", "name: broken\nconduit: c\nschedule:\n  type: bogus\n")
    await daemon.start()
    assert {p.name for p in daemon.list_planned()} == {"good"}
    assert len(daemon.load_errors) == 1
    assert daemon.load_errors[0].source_path.name == "broken.yaml"


# -------------------------------------------------------------- sync / hot reload


async def test_sync_picks_up_added_schedules(daemon, store):
    await daemon.start()
    assert daemon.list_planned() == []
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon._sync_from_disk()
    assert [p.name for p in daemon.list_planned()] == ["weekly"]


async def test_sync_drops_removed_schedules(daemon, store):
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon.start()
    store.remove("weekly")
    await daemon._sync_from_disk()
    assert daemon.list_planned() == []


async def test_sync_updates_on_mtime_change(daemon, store):
    path = _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon.start()
    job_before = daemon._scheduler.get_job("weekly")
    next_before = job_before.next_run_time
    # Rewrite with a different hour and bump mtime.
    path.write_text(
        RECURRING_FAR_FUTURE.replace('"09:00"', '"17:30"')
    )
    import os, time
    future = path.stat().st_mtime + 5
    os.utime(path, (future, future))
    await daemon._sync_from_disk()
    next_after = daemon._scheduler.get_job("weekly").next_run_time
    assert next_after.hour == 17 and next_after.minute == 30
    assert next_after != next_before


async def test_sync_reload_job_is_preserved(daemon, store):
    await daemon.start()
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon._sync_from_disk()
    job_ids = {j.id for j in daemon._scheduler.get_jobs()}
    assert _RELOAD_JOB_ID in job_ids
    assert "weekly" in job_ids


# -------------------------------------------------------------- fire


async def test_fire_invokes_executor_with_resolved_working_dir(
    daemon, store, executor, tmp_path
):
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon.start()
    await daemon._fire("weekly")
    assert len(executor.calls) == 1
    definition, working_dir = executor.calls[0]
    assert definition.name == "weekly"
    assert definition.conduit == "report"
    assert working_dir == tmp_path.resolve()


async def test_fire_uses_relative_working_dir(daemon, store, executor, tmp_path):
    proj = tmp_path / "projects" / "foo"
    proj.mkdir(parents=True)
    body = (
        "conduit: report\n"
        "working_dir: projects/foo\n"
        "schedule:\n  type: recurring\n  days: [mon]\n  hours: ['09:00']\n"
    )
    _write(store, "scoped", body)
    await daemon.start()
    await daemon._fire("scoped")
    _, working_dir = executor.calls[0]
    assert working_dir == proj.resolve()


async def test_fire_passes_inputs(daemon, store, executor):
    body = (
        "conduit: report\n"
        "inputs:\n  date: today\n  region: us\n"
        "schedule:\n  type: recurring\n  days: [mon]\n  hours: ['09:00']\n"
    )
    _write(store, "with_inputs", body)
    await daemon.start()
    await daemon._fire("with_inputs")
    definition, _ = executor.calls[0]
    assert definition.inputs == {"date": "today", "region": "us"}


async def test_fire_marks_one_shot_fired_state(daemon, store, executor):
    _write(store, "once", ONCE_FAR_FUTURE)
    await daemon.start()
    await daemon._fire("once")
    assert store.fired_at("once") == "2099-05-01T09:00:00"


async def test_fire_does_not_mark_state_for_recurring(daemon, store, executor):
    _write(store, "weekly", RECURRING_FAR_FUTURE)
    await daemon.start()
    await daemon._fire("weekly")
    assert store.fired_at("weekly") is None


async def test_fire_failure_does_not_mark_state(daemon, store, executor):
    _write(store, "once", ONCE_FAR_FUTURE)
    await daemon.start()
    executor.raise_on_next = True
    await daemon._fire("once")  # must NOT raise
    assert store.fired_at("once") is None


async def test_fire_skips_when_yaml_disappears(daemon, store, executor):
    _write(store, "ghost", RECURRING_FAR_FUTURE)
    await daemon.start()
    store.remove("ghost")
    # No executor call, no exception.
    await daemon._fire("ghost")
    assert executor.calls == []


# -------------------------------------------------------------- one-shot fired-state skipping


async def test_already_fired_one_shot_is_not_re_registered(
    daemon, store, executor
):
    _write(store, "once", ONCE_FAR_FUTURE)
    store.mark_fired("once", "2099-05-01T09:00:00")
    await daemon.start()
    assert daemon._scheduler.get_job("once") is None
    assert "once" not in {p.name for p in daemon.list_planned()}


async def test_changing_one_shot_at_re_arms_after_fire(daemon, store, executor):
    _write(store, "once", ONCE_FAR_FUTURE)
    store.mark_fired("once", "2099-05-01T09:00:00")
    await daemon.start()
    assert daemon._scheduler.get_job("once") is None
    # User edits the YAML to a new datetime.
    path = store.path_for("once")
    path.write_text(ONCE_OTHER_TIME)
    import os
    future = path.stat().st_mtime + 5
    os.utime(path, (future, future))
    await daemon._sync_from_disk()
    assert daemon._scheduler.get_job("once") is not None


# -------------------------------------------------------------- fire concurrency


async def test_fire_runs_concurrently_for_distinct_schedules(
    daemon, store, executor
):
    _write(store, "a", RECURRING_FAR_FUTURE)
    _write(store, "b", RECURRING_FAR_FUTURE.replace("report", "report2"))
    await daemon.start()
    await asyncio.gather(daemon._fire("a"), daemon._fire("b"))
    names = {c[0].name for c in executor.calls}
    assert names == {"a", "b"}
