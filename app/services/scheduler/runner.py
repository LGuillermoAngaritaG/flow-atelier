"""Async scheduler daemon driven by the JSON-backed ScheduleStore."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.schemas.api import ScheduledJob
from app.services.scheduler.store import ScheduleStore
from app.services.scheduler.triggers import default_local_zone, to_trigger

logger = logging.getLogger(__name__)


# Job ID reserved for the periodic reload job.
_RELOAD_JOB_ID = "__atelier_sync__"


ScheduleExecutor = Callable[[ScheduledJob, Path], Awaitable[None]]


async def _default_executor(job: ScheduledJob, working_dir: Path) -> None:
    """Default fire action: instantiate ``Atelier(base_dir=working_dir/.atelier)``
    and ``await run_conduit(...)``. Imported lazily to avoid a circular import.

    :param job: schedule being fired
    :param working_dir: directory under which ``.atelier`` is resolved
    """
    from app.core.atelier import Atelier

    atelier = Atelier(base_dir=working_dir / ".atelier")
    await atelier.run_conduit(job.conduit_name, dict(job.inputs))


@dataclass(frozen=True)
class PlannedJob:
    """A schedule currently registered with the daemon."""

    id: str
    name: str
    conduit_name: str
    next_fire_time: datetime | None
    working_dir: Path
    schedule_kind: str  # "once" | "recurring"


class SchedulerDaemon:
    """JSON-driven async scheduler.

    Holds an :class:`AsyncIOScheduler`, syncs the live job set against the
    schedule store on a fixed reload interval, and dispatches each fire by
    calling the configured executor with a fresh :class:`Atelier`.

    :param store: backing :class:`ScheduleStore`
    :param executor: per-fire coroutine; defaults to running the conduit
    :param default_zone: default timezone for naive ``run_at`` values
    :param default_working_dir: fallback working dir if ``run_path`` is empty
    :param reload_interval_seconds: how often to re-scan the store
    """

    def __init__(
        self,
        store: ScheduleStore,
        *,
        executor: ScheduleExecutor | None = None,
        default_zone: ZoneInfo | None = None,
        default_working_dir: Path | None = None,
        reload_interval_seconds: float = 30.0,
    ) -> None:
        """Configure the daemon without starting it.

        :param store: backing :class:`ScheduleStore`
        :param executor: per-fire coroutine; defaults to running the conduit
        :param default_zone: default timezone for naive ``run_at`` values
        :param default_working_dir: fallback working dir if ``run_path`` is empty
        :param reload_interval_seconds: how often to re-scan the store
        """
        self.store = store
        self.executor: ScheduleExecutor = executor or _default_executor
        self.default_zone = default_zone or default_local_zone()
        self.default_working_dir = (default_working_dir or Path.cwd()).resolve()
        self.reload_interval_seconds = reload_interval_seconds
        self._scheduler: AsyncIOScheduler | None = None
        self._planned: dict[str, PlannedJob] = {}

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Boot the APScheduler, install the reload job, and sync from disk."""
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler(timezone=self.default_zone)
        self._scheduler.add_job(
            self._sync_from_disk,
            trigger=IntervalTrigger(seconds=self.reload_interval_seconds),
            id=_RELOAD_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        await self._sync_from_disk()
        self._scheduler.start()
        logger.info(
            "scheduler started: %d schedule(s), tz=%s, reload=%.1fs",
            len(self._planned),
            self.default_zone,
            self.reload_interval_seconds,
        )

    async def stop(self) -> None:
        """Shut down the APScheduler if it is currently running."""
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("scheduler stopped")

    async def run_forever(self) -> None:
        """Start the daemon and block until SIGINT/SIGTERM."""
        await self.start()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        installed: list[int] = []
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                    installed.append(sig)
                except (NotImplementedError, RuntimeError):
                    pass
        try:
            await stop_event.wait()
        finally:
            for sig in installed:
                try:
                    loop.remove_signal_handler(sig)
                except Exception:  # noqa: BLE001
                    pass
            await self.stop()

    # ------------------------------------------------------------------ sync

    async def _sync_from_disk(self) -> None:
        """Diff live jobs against active schedules; add/update/remove as needed."""
        if self._scheduler is None:
            return
        active = {j.id: j for j in self.store.list()}
        live_ids = {
            job.id
            for job in self._scheduler.get_jobs()
            if job.id != _RELOAD_JOB_ID
        }

        for stale in live_ids - active.keys():
            self._scheduler.remove_job(stale)
            self._planned.pop(stale, None)
            logger.info("removed schedule %s (not active)", stale)

        for sid, job in active.items():
            if job.schedule.mode == "once" and self.store.fired_at(sid):
                # Skip already-fired one-shots (regardless of whether the
                # daemon was previously running).
                if sid in live_ids:
                    self._scheduler.remove_job(sid)
                self._planned.pop(sid, None)
                continue
            self._register(job)

    def _register(self, job: ScheduledJob) -> None:
        """Register or replace the APScheduler job for ``job`` and cache planning data.

        :param job: schedule to (re-)register
        """
        assert self._scheduler is not None
        trigger = to_trigger(job, default_zone=self.default_zone)
        working_dir = self._resolve_working_dir(job)
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        now = datetime.now(tz=self.default_zone)
        next_fire = trigger.get_next_fire_time(None, now)
        self._planned[job.id] = PlannedJob(
            id=job.id,
            name=job.schedule.name or job.id,
            conduit_name=job.conduit_name,
            next_fire_time=next_fire,
            working_dir=working_dir,
            schedule_kind=job.schedule.mode,
        )
        logger.info(
            "registered schedule %s (%s): next fire %s",
            job.id,
            job.schedule.mode,
            next_fire,
        )

    def _resolve_working_dir(self, job: ScheduledJob) -> Path:
        """Resolve ``job.run_path`` against the configured default working dir.

        :param job: schedule whose working directory should be resolved
        """
        if not job.run_path:
            return self.default_working_dir
        wd = Path(job.run_path)
        if not wd.is_absolute():
            wd = (self.default_working_dir / wd).resolve()
        return wd

    # ------------------------------------------------------------------ fire

    async def _fire(self, schedule_id: str) -> None:
        """Job function: re-read the latest schedule and dispatch it.

        ``once`` schedules are marked fired regardless of executor outcome
        so a single failure does not turn into an infinite retry loop.
        ``runs_completed`` only advances when the executor returns cleanly.

        :param schedule_id: schedule identifier passed by APScheduler
        """
        job = self.store.get(schedule_id)
        if job is None:
            logger.warning(
                "schedule %s not present before firing; skipping", schedule_id
            )
            return
        working_dir = self._resolve_working_dir(job)
        logger.info(
            "firing schedule %s → %s in %s",
            schedule_id,
            job.conduit_name,
            working_dir,
        )
        succeeded = False
        try:
            await self.executor(job, working_dir)
            succeeded = True
        except Exception:  # noqa: BLE001 — daemon must survive a single failed fire
            logger.exception("schedule %s failed", schedule_id)
        finally:
            if job.schedule.mode == "once":
                self.store.mark_fired(schedule_id)
        if succeeded:
            self.store.increment_runs(schedule_id)

    # ------------------------------------------------------------------ introspection

    def list_planned(self) -> list[PlannedJob]:
        """Return the schedules currently registered with the daemon."""
        return sorted(self._planned.values(), key=lambda p: p.id)


def compute_planned_view(
    store: ScheduleStore,
    *,
    default_zone: ZoneInfo,
    default_working_dir: Path,
) -> list[PlannedJob]:
    """Compute next-fire-time for every active schedule on disk.

    Used by ``atelier schedule list`` and ``atelier scheduler status`` so they
    work whether or not a daemon is running. Already-fired one-shots are
    surfaced with ``next_fire_time=None``.

    :param store: schedule store to read from
    :param default_zone: timezone used to evaluate cron/date triggers
    :param default_working_dir: base directory used to resolve relative ``run_path``
    """
    now = datetime.now(tz=default_zone)
    base = default_working_dir.resolve()
    planned: list[PlannedJob] = []
    for job in store.list():
        run_path = job.run_path
        if run_path:
            wd = Path(run_path)
            working_dir = wd if wd.is_absolute() else (base / wd).resolve()
        else:
            working_dir = base
        if job.schedule.mode == "once" and store.fired_at(job.id):
            planned.append(
                PlannedJob(
                    id=job.id,
                    name=job.schedule.name or job.id,
                    conduit_name=job.conduit_name,
                    next_fire_time=None,
                    working_dir=working_dir,
                    schedule_kind="once",
                )
            )
            continue
        trigger = to_trigger(job, default_zone=default_zone)
        next_fire = trigger.get_next_fire_time(None, now)
        planned.append(
            PlannedJob(
                id=job.id,
                name=job.schedule.name or job.id,
                conduit_name=job.conduit_name,
                next_fire_time=next_fire,
                working_dir=working_dir,
                schedule_kind=job.schedule.mode,
            )
        )
    planned.sort(key=lambda p: p.id)
    return planned
