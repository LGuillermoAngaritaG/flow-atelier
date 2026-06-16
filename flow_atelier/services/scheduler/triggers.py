"""Convert :class:`ScheduledJob` records into APScheduler triggers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from flow_atelier.schemas.api import ScheduledJob

# ISO 8601 day-of-week (1=Mon..7=Sun) → APScheduler cron day_of_week names.
_ISO_DAY_TO_CRON = {
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun",
}


def default_local_zone() -> ZoneInfo:
    """Resolve the host's local IANA timezone, with a UTC fallback."""
    try:
        import tzlocal
    except ImportError:  # pragma: no cover — declared as a dep
        tzlocal = None
    if tzlocal is not None:
        try:
            zone = tzlocal.get_localzone()
            if isinstance(zone, ZoneInfo):
                return zone
            name = getattr(zone, "key", None) or str(zone)
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    fallback = datetime.now().astimezone().tzinfo
    name = getattr(fallback, "key", None) or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def to_trigger(job: ScheduledJob, default_zone: ZoneInfo) -> BaseTrigger:
    """Build an APScheduler trigger for ``job``.

    :param job: persisted schedule
    :param default_zone: timezone used when the schedule pins none and for
        naive ``run_at`` values
    :returns: ``DateTrigger`` for ``mode="once"``; ``IntervalTrigger`` for
        ``mode="interval"``; ``CronTrigger`` (or ``OrTrigger`` of crons) for
        ``mode="recurring"``
    """
    schedule = job.schedule
    zone = ZoneInfo(schedule.timezone) if schedule.timezone else default_zone
    if schedule.mode == "interval":
        assert schedule.every_minutes is not None  # validated upstream
        return IntervalTrigger(minutes=schedule.every_minutes, timezone=zone)
    if schedule.mode == "once":
        run_at = schedule.run_at
        assert run_at is not None  # validated upstream
        run_date = (
            run_at if run_at.tzinfo is not None else run_at.replace(tzinfo=zone)
        )
        return DateTrigger(run_date=run_date, timezone=zone)
    days = schedule.days or []
    times = schedule.times or []
    day_of_week = ",".join(_ISO_DAY_TO_CRON[d] for d in days)
    crons: list[CronTrigger] = []
    for t in times:
        hour_str, minute_str = t.split(":")
        crons.append(
            CronTrigger(
                day_of_week=day_of_week,
                hour=int(hour_str),
                minute=int(minute_str),
                second=0,
                timezone=zone,
            )
        )
    if len(crons) == 1:
        return crons[0]
    return OrTrigger(crons)
