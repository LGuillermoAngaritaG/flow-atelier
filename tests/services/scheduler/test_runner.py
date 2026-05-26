"""SchedulerDaemon: sync, fire, and one-shot fired-state tests (JSON store)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.schemas.api import CreateScheduleInput, ScheduledJob
from app.services.scheduler.runner import _RELOAD_JOB_ID, SchedulerDaemon
from app.services.scheduler.store import ScheduleStore

UTC = ZoneInfo("UTC")


def _recurring(conduit: str = "report") -> CreateScheduleInput:
    """Build a recurring CreateScheduleInput for the given conduit.

    :param conduit: conduit name to embed in the schedule payload.
    """
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
    """Build a once-mode CreateScheduleInput firing at the given timestamp.

    :param at_iso: ISO-8601 timestamp for the one-shot run.
    """
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
    """Provide a ScheduleStore rooted at a temp .atelier directory.

    :param tmp_path: pytest temp directory fixture.
    """
    return ScheduleStore(tmp_path / ".atelier")


class _RecordingExecutor:
    def __init__(self) -> None:
        """Initialize a recording executor with empty call history."""
        self.calls: list[tuple[ScheduledJob, Path]] = []
        self.raise_on_next = False

    async def __call__(self, job: ScheduledJob, working_dir: Path) -> None:
        """Record an execution and optionally raise to simulate failure.

        :param job: scheduled job being fired.
        :param working_dir: working directory for the run.
        """
        self.calls.append((job, working_dir))
        if self.raise_on_next:
            self.raise_on_next = False
            raise RuntimeError("forced failure for test")


@pytest.fixture
def executor() -> _RecordingExecutor:
    """Provide a fresh recording executor."""
    return _RecordingExecutor()


@pytest.fixture
async def daemon(tmp_path, store, executor):
    """Provide a started/stopped SchedulerDaemon wired to the test store and executor.

    :param tmp_path: pytest temp directory fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
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
    """Verify start() registers all pre-existing schedules.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    """
    a = store.create(_recurring("a"))
    b = store.create(_once())
    await daemon.start()
    planned = {p.id for p in daemon.list_planned()}
    assert planned == {a.id, b.id}


async def test_start_is_idempotent(daemon, store):
    """Verify calling start() twice does not duplicate jobs.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    await daemon.start()
    assert {p.id for p in daemon.list_planned()} == {job.id}


async def test_start_with_no_schedules(daemon):
    """Verify start() handles an empty store gracefully.

    :param daemon: SchedulerDaemon fixture.
    """
    await daemon.start()
    assert daemon.list_planned() == []


# -------------------------------------------------------------- sync / hot reload


async def test_sync_picks_up_added_schedules(daemon, store):
    """Verify _sync_from_disk picks up schedules added after start.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    """
    await daemon.start()
    assert daemon.list_planned() == []
    job = store.create(_recurring())
    await daemon._sync_from_disk()
    assert [p.id for p in daemon.list_planned()] == [job.id]


async def test_sync_drops_deleted_schedules(daemon, store):
    """Verify _sync_from_disk drops schedules deleted from the store.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    store.delete(job.id)
    await daemon._sync_from_disk()
    assert daemon.list_planned() == []


async def test_sync_reload_job_is_preserved(daemon, store):
    """Verify the internal reload job remains scheduled after sync.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    """
    await daemon.start()
    store.create(_recurring())
    await daemon._sync_from_disk()
    job_ids = {j.id for j in daemon._scheduler.get_jobs()}
    assert _RELOAD_JOB_ID in job_ids


# -------------------------------------------------------------- fire


async def test_fire_invokes_executor_with_run_path(daemon, store, executor):
    """Verify _fire invokes the executor with the schedule's run_path.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    assert len(executor.calls) == 1
    fired_job, working_dir = executor.calls[0]
    assert fired_job.id == job.id
    assert fired_job.conduit_name == "report"
    assert working_dir == Path("/tmp/run")


async def test_fire_passes_inputs(daemon, store, executor):
    """Verify _fire passes the schedule's inputs to the executor.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
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
    """Verify _fire marks fired-state for one-shot schedules.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_once())
    await daemon.start()
    await daemon._fire(job.id)
    assert store.fired_at(job.id) is not None


async def test_fire_does_not_mark_state_for_recurring(daemon, store, executor):
    """Verify _fire does not mark fired-state for recurring schedules.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    assert store.fired_at(job.id) is None


async def test_fire_failure_still_marks_one_shot_fired(daemon, store, executor):
    """A failed one-shot fire MUST mark fired-state so it does not retry forever.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_once())
    await daemon.start()
    executor.raise_on_next = True
    await daemon._fire(job.id)  # must NOT raise
    assert store.fired_at(job.id) is not None


async def test_fire_failure_does_not_increment_runs(daemon, store, executor):
    """A failed fire MUST NOT advance the runs_completed counter.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    executor.raise_on_next = True
    await daemon._fire(job.id)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.runs_completed == 0


async def test_fire_skips_deleted_schedules(daemon, store, executor):
    """Verify _fire skips schedules that have been deleted.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    store.delete(job.id)
    await daemon._fire(job.id)
    assert executor.calls == []


async def test_fire_increments_runs_completed(daemon, store, executor):
    """Verify a successful fire increments runs_completed.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_recurring())
    await daemon.start()
    await daemon._fire(job.id)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.runs_completed == 1


# -------------------------------------------------------------- one-shot fired skipping


async def test_already_fired_one_shot_is_not_registered(daemon, store, executor):
    """Verify an already-fired one-shot is not re-registered on start.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    job = store.create(_once())
    store.mark_fired(job.id)
    await daemon.start()
    assert daemon._scheduler.get_job(job.id) is None


# -------------------------------------------------------------- concurrency


async def test_fire_runs_concurrently_for_distinct_schedules(
    daemon, store, executor
):
    """Verify _fire can run concurrently for distinct schedules.

    :param daemon: SchedulerDaemon fixture.
    :param store: ScheduleStore fixture.
    :param executor: recording executor fixture.
    """
    a = store.create(_recurring("a"))
    b = store.create(_recurring("b"))
    await daemon.start()
    await asyncio.gather(daemon._fire(a.id), daemon._fire(b.id))
    ids = {c[0].id for c in executor.calls}
    assert ids == {a.id, b.id}
