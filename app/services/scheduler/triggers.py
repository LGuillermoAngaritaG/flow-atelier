"""Convert schedule specs into APScheduler triggers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.schemas.schedule import (
    OnceSchedule,
    RecurringSchedule,
    ScheduleDefinition,
)


def default_local_zone() -> ZoneInfo:
    """Resolve the host's local IANA timezone, with a UTC fallback.

    Tries ``tzlocal.get_localzone()`` first because it normalizes Windows
    "Pacific Standard Time"-style names to ``America/Los_Angeles``. Falls
    back to whatever ``datetime.now().astimezone()`` gives us if tzlocal
    is unavailable or returns a non-IANA zone.
    """
    try:
        import tzlocal  # local import: optional perf cost only on first call
    except ImportError:  # pragma: no cover — declared as a dep
        tzlocal = None
    if tzlocal is not None:
        try:
            zone = tzlocal.get_localzone()
            if isinstance(zone, ZoneInfo):
                return zone
            name = getattr(zone, "key", None) or str(zone)
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 — fall through to system clock zone
            pass
    fallback = datetime.now().astimezone().tzinfo
    name = getattr(fallback, "key", None) or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def to_trigger(definition: ScheduleDefinition, default_zone: ZoneInfo) -> BaseTrigger:
    """Build an APScheduler trigger from a parsed schedule definition.

    :param definition: validated schedule
    :param default_zone: timezone used when the schedule omits ``timezone:``
    :returns: ``DateTrigger`` for ``once``, ``CronTrigger`` (or
        ``OrTrigger`` of crons) for ``recurring``
    """
    zone = definition.resolve_zone(default_zone)
    spec = definition.schedule
    if isinstance(spec, OnceSchedule):
        run_date = spec.at if spec.at.tzinfo is not None else spec.at.replace(tzinfo=zone)
        return DateTrigger(run_date=run_date, timezone=zone)
    if isinstance(spec, RecurringSchedule):
        day_of_week = ",".join(spec.days)
        crons = [
            CronTrigger(
                day_of_week=day_of_week,
                hour=t.hour,
                minute=t.minute,
                second=t.second,
                timezone=zone,
            )
            for t in spec.hours
        ]
        if len(crons) == 1:
            return crons[0]
        return OrTrigger(crons)
    raise TypeError(f"unsupported schedule spec: {spec!r}")  # pragma: no cover
