"""Async scheduler daemon driven by .atelier/schedules YAML."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.schemas.schedule import OnceSchedule, ScheduleDefinition
from app.services.scheduler.store import (
    LoadedSchedule,
    ScheduleLoadError,
    ScheduleStore,
)
from app.services.scheduler.triggers import default_local_zone, to_trigger


logger = logging.getLogger(__name__)


# Job ID reserved for the periodic reload job.
_RELOAD_JOB_ID = "__atelier_sync__"


ScheduleExecutor = Callable[[ScheduleDefinition, Path], Awaitable[None]]


async def _default_executor(definition: ScheduleDefinition, working_dir: Path) -> None:
    """Default fire action: instantiate ``Atelier(base_dir=working_dir/.atelier)``
    and ``await run_conduit(...)``. Imported lazily to keep test-time
    bootstrapping cheap and to avoid a circular import.
    """
    from app.core.atelier import Atelier  # local import: avoids cycle at scheduler import time

    atelier = Atelier(base_dir=working_dir / ".atelier")
    await atelier.run_conduit(definition.conduit, dict(definition.inputs))


@dataclass(frozen=True)
class PlannedJob:
    """A schedule that is currently registered with the daemon."""

    name: str
    conduit: str
    next_fire_time: datetime | None
    working_dir: Path
    schedule_kind: str  # "once" | "recurring"


class SchedulerDaemon:
    """YAML-driven async scheduler.

    Holds an :class:`AsyncIOScheduler`, syncs the live job set against
    the contents of ``store.schedules_dir`` on startup and on a fixed
    reload interval, and dispatches each fire by calling the configured
    executor with a fresh :class:`Atelier`.

    The daemon is a thin coordinator — it never blocks on a running flow
    (APScheduler runs each fire as its own task), and it never owns flow
    state. All persistence is the existing filesystem store under each
    schedule's ``working_dir``.
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
        self.store = store
        self.executor: ScheduleExecutor = executor or _default_executor
        self.default_zone = default_zone or default_local_zone()
        self.default_working_dir = (default_working_dir or Path.cwd()).resolve()
        self.reload_interval_seconds = reload_interval_seconds
        self._scheduler: AsyncIOScheduler | None = None
        self._known_mtimes: dict[str, float] = {}
        # Cached after each sync; the CLI's `scheduler status` reads this
        # to render a table without re-parsing every YAML file.
        self._planned: dict[str, PlannedJob] = {}
        self._load_errors: list[ScheduleLoadError] = []

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
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
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("scheduler stopped")

    async def run_forever(self) -> None:
        """Start the daemon and block until SIGINT/SIGTERM (or Ctrl+C)."""
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
        """Diff live jobs against on-disk YAML; add/update/remove as needed."""
        if self._scheduler is None:
            # Initial sync runs *before* scheduler.start() so
            # self._scheduler is set; the early-return only matters if a
            # caller manually invokes sync after stop().
            return
        loaded, errors = self.store.list_definitions_with_errors()
        self._load_errors = errors
        for err in errors:
            logger.warning("skipping unparseable schedule %s: %s", err.source_path, err.error)

        on_disk: dict[str, LoadedSchedule] = {ls.definition.name: ls for ls in loaded}
        live_ids = {
            job.id
            for job in self._scheduler.get_jobs()
            if job.id != _RELOAD_JOB_ID
        }

        # Remove jobs whose YAML has been deleted.
        for stale in live_ids - on_disk.keys():
            self._scheduler.remove_job(stale)
            self._known_mtimes.pop(stale, None)
            self._planned.pop(stale, None)
            logger.info("removed schedule %s (yaml deleted)", stale)

        # Add or update jobs from YAML.
        for name, ls in on_disk.items():
            prior_mtime = self._known_mtimes.get(name)
            if name in live_ids and prior_mtime == ls.mtime:
                continue
            self._register(ls)

    def _register(self, ls: LoadedSchedule) -> None:
        assert self._scheduler is not None
        definition = ls.definition

        # Skip already-fired one-shots so a daemon restart doesn't re-run them.
        if isinstance(definition.schedule, OnceSchedule):
            already = self.store.fired_at(definition.name)
            if already and already == definition.schedule.at.isoformat():
                logger.info(
                    "skipping one-shot %s: already fired for at=%s",
                    definition.name,
                    already,
                )
                if definition.name in {j.id for j in self._scheduler.get_jobs()}:
                    self._scheduler.remove_job(definition.name)
                self._known_mtimes[definition.name] = ls.mtime
                self._planned.pop(definition.name, None)
                return

        trigger = to_trigger(definition, default_zone=self.default_zone)
        working_dir = self._resolve_working_dir(definition)
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=definition.name,
            args=[definition.name],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._known_mtimes[definition.name] = ls.mtime
        # Compute next fire time from the trigger directly: APScheduler
        # only populates Job.next_run_time *after* scheduler.start(), and
        # the initial sync runs before that.
        now = datetime.now(tz=self.default_zone)
        next_fire = trigger.get_next_fire_time(None, now)
        self._planned[definition.name] = PlannedJob(
            name=definition.name,
            conduit=definition.conduit,
            next_fire_time=next_fire,
            working_dir=working_dir,
            schedule_kind=definition.schedule.type,
        )
        logger.info(
            "registered schedule %s (%s): next fire %s",
            definition.name,
            definition.schedule.type,
            next_fire,
        )

    def _resolve_working_dir(self, definition: ScheduleDefinition) -> Path:
        if definition.working_dir is None:
            return self.default_working_dir
        wd = Path(definition.working_dir)
        if not wd.is_absolute():
            wd = (self.default_working_dir / wd).resolve()
        return wd

    # ------------------------------------------------------------------ fire

    async def _fire(self, name: str) -> None:
        """Job function: re-read the latest definition and dispatch it."""
        try:
            definition = self.store.read(name)
        except FileNotFoundError:
            logger.warning("schedule %s vanished before firing; skipping", name)
            return
        working_dir = self._resolve_working_dir(definition)
        scheduled_at = (
            definition.schedule.at.isoformat()
            if isinstance(definition.schedule, OnceSchedule)
            else None
        )
        logger.info("firing schedule %s → %s in %s", name, definition.conduit, working_dir)
        try:
            await self.executor(definition, working_dir)
        except Exception:  # noqa: BLE001 — daemon must survive a single failed fire
            logger.exception("schedule %s failed", name)
            return
        if scheduled_at is not None:
            self.store.mark_fired(name, scheduled_at)

    # ------------------------------------------------------------------ introspection

    def list_planned(self) -> list[PlannedJob]:
        """Return the schedules currently registered with the daemon."""
        return sorted(self._planned.values(), key=lambda p: p.name)

    @property
    def load_errors(self) -> list[ScheduleLoadError]:
        return list(self._load_errors)


def compute_planned_view(
    store: ScheduleStore,
    *,
    default_zone: ZoneInfo,
    default_working_dir: Path,
) -> tuple[list[PlannedJob], list[ScheduleLoadError]]:
    """Compute next-fire-time for every schedule on disk.

    Used by ``atelier schedule list`` and ``atelier scheduler status`` so
    they work whether or not a daemon is running. Already-fired one-shots
    are surfaced with ``next_fire_time=None``.
    """
    loaded, errors = store.list_definitions_with_errors()
    now = datetime.now(tz=default_zone)
    base = default_working_dir.resolve()
    planned: list[PlannedJob] = []
    for ls in loaded:
        d = ls.definition
        wd = d.working_dir
        working_dir = base if wd is None else (
            Path(wd) if Path(wd).is_absolute() else (base / wd).resolve()
        )
        if isinstance(d.schedule, OnceSchedule):
            already = store.fired_at(d.name)
            if already and already == d.schedule.at.isoformat():
                planned.append(
                    PlannedJob(
                        name=d.name,
                        conduit=d.conduit,
                        next_fire_time=None,
                        working_dir=working_dir,
                        schedule_kind="once",
                    )
                )
                continue
        trigger = to_trigger(d, default_zone=default_zone)
        next_fire = trigger.get_next_fire_time(None, now)
        planned.append(
            PlannedJob(
                name=d.name,
                conduit=d.conduit,
                next_fire_time=next_fire,
                working_dir=working_dir,
                schedule_kind=d.schedule.type,
            )
        )
    planned.sort(key=lambda p: p.name)
    return planned, errors
