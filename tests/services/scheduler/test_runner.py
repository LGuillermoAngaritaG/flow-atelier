"""SchedulerDaemon: sync, fire, and one-shot fired-state tests (JSON store)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.schemas.api import CreateScheduleInput, ScheduledJob
from app.services.scheduler.runner import SchedulerDaemon, _RELOAD_JOB_ID
from app.services.scheduler.store import ScheduleStore


UTC = ZoneInfo("UTC")


def _recurring(conduit: str = "report") -> CreateScheduleInput:
    return CreateScheduleInput.model_validate(
        {
            "conduit_name": conduit,
            "inputs": {},
            "run_path": "/tmp/run",
            "schedule": {
                "mode": "recurring",
                "name": conduit,
                "days": [1],  # Monday
                "times": ["09:00"],
            },
        }
    )


def _once(at_iso: str = "2099-05-01T09:00:00Z") -> CreateScheduleInput:
    return CreateScheduleInput.model_validate(
        {
            "conduit_name": "backfill",
            "inputs": {},
            "run_path": "/tmp/run",
            "schedule": {
                "mode": "once",
                "name": "backfill_once",
                "run_at": at_iso,
            },
        }
    )


@pytest.fixture
def store(tmp_path) -> ScheduleStore:
    return ScheduleStore(tmp_path / ".atelier")


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[ScheduledJob, Path]] = []
        self.raise_on_next = False

    async def __call__(self, job: ScheduledJob, working_dir: Path) -> None:
        self.calls.append((job, working_dir))
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
        reload_interval_seconds=3600,
    )
    yield d
    await d.stop()


# -------------------------------------------------------------- start / stop


async def test_start_registers_existing_schedules(daemon, store):
    a = store.create(_recurring("a"))
    b = store.create(_once())
    await daemon.start()
    planned = {p.id for p in daemon.list_planned()}
    assert planned == {a.id, b.id}


async def test_start_is_idempotent(daemon, store):
    job = store.create(_recurring())
    await daemon.start()
    await daemon.start()
    assert {p.id for p in daemon.list_planned()} == {job.id}


async def test_start_with_no_schedules(daemon):
    await daemon.start()
    assert daemon.list_planned() == []


# -------------------------------------------------------------- sync / hot reload


async def test_sync_picks_up_added_schedules(daemon, store):
    await daemon.start()
    assert daemon.list_planned() == []
    job = store.create(_recurring())
    await daemon._sync_from_disk()
    assert [p.id for p in daemon.list_planned()] == [job.id]


async def test_sync_drops_deleted_schedules(daemon, store):
    job = store.create(_recurring())
    await daemon.start()
    store.delete(job.id)
    await daemon._sync_from_disk()
    assert daemon.list_planned() == []


async def test_sync_reload_job_is_preserved(daemon, store):
    await daemon.start()
    store.create(_recurring())
    await daemon._sync_from_disk()
    job_ids = {j.id for j in daemon._scheduler.get_jobs()}
    assert _RELOAD_JOB_ID in job_ids


# -------------------------------------------------------------- fire


async def test_fire_invokes_executor_with_run_path(daemon, store, executor):
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    assert len(executor.calls) == 1
    fired_job, working_dir = executor.calls[0]
    assert fired_job.id == job.id
    assert fired_job.conduit_name == "report"
    assert working_dir == Path("/tmp/run")


async def test_fire_passes_inputs(daemon, store, executor):
    payload = CreateScheduleInput.model_validate(
        {
            "conduit_name": "report",
            "inputs": {"date": "today", "region": "us"},
            "run_path": "/tmp/run",
            "schedule": {
                "mode": "recurring",
                "name": "x",
                "days": [1],
                "times": ["09:00"],
            },
        }
    )
    job = store.create(payload)
    await daemon.start()
    await daemon._fire(job.id)
    fired_job, _ = executor.calls[0]
    assert fired_job.inputs == {"date": "today", "region": "us"}


async def test_fire_marks_one_shot_fired_state(daemon, store, executor):
    job = store.create(_once())
    await daemon.start()
    await daemon._fire(job.id)
    assert store.fired_at(job.id) is not None


async def test_fire_does_not_mark_state_for_recurring(daemon, store, executor):
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    assert store.fired_at(job.id) is None


async def test_fire_failure_does_not_mark_state(daemon, store, executor):
    job = store.create(_once())
    await daemon.start()
    executor.raise_on_next = True
    await daemon._fire(job.id)  # must NOT raise
    assert store.fired_at(job.id) is None


async def test_fire_skips_deleted_schedules(daemon, store, executor):
    job = store.create(_recurring())
    await daemon.start()
    store.delete(job.id)
    await daemon._fire(job.id)
    assert executor.calls == []


async def test_fire_increments_runs_completed(daemon, store, executor):
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.runs_completed == 1


# -------------------------------------------------------------- one-shot fired skipping


async def test_already_fired_one_shot_is_not_registered(daemon, store, executor):
    job = store.create(_once())
    store.mark_fired(job.id)
    await daemon.start()
    assert daemon._scheduler.get_job(job.id) is None


# -------------------------------------------------------------- concurrency


async def test_fire_runs_concurrently_for_distinct_schedules(
    daemon, store, executor
):
    a = store.create(_recurring("a"))
    b = store.create(_recurring("b"))
    await daemon.start()
    await asyncio.gather(daemon._fire(a.id), daemon._fire(b.id))
    ids = {c[0].id for c in executor.calls}
    assert ids == {a.id, b.id}
