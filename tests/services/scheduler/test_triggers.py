"""Tests for trigger construction (APScheduler integration)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.schemas.schedule import ScheduleDefinition
from app.services.scheduler.triggers import default_local_zone, to_trigger


UTC = ZoneInfo("UTC")
NYC = ZoneInfo("America/New_York")


def _def(payload: dict) -> ScheduleDefinition:
    return ScheduleDefinition.model_validate(payload)


# -------------------------------------------------------------- once


def test_once_naive_uses_default_zone():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {"type": "once", "at": "2026-05-01T09:00:00"},
    })
    trig = to_trigger(sd, default_zone=UTC)
    assert isinstance(trig, DateTrigger)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 1, tzinfo=UTC))
    assert fire == datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


def test_once_naive_uses_per_schedule_timezone_override():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "timezone": "America/New_York",
        "schedule": {"type": "once", "at": "2026-05-01T09:00:00"},
    })
    trig = to_trigger(sd, default_zone=UTC)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 1, tzinfo=UTC))
    assert fire.astimezone(NYC) == datetime(2026, 5, 1, 9, 0, tzinfo=NYC)


def test_once_aware_at_keeps_its_tz():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {"type": "once", "at": "2026-05-01T09:00:00Z"},
    })
    trig = to_trigger(sd, default_zone=NYC)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 1, tzinfo=UTC))
    assert fire == datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)


# -------------------------------------------------------------- recurring


def test_recurring_single_hour_returns_cron():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    trig = to_trigger(sd, default_zone=UTC)
    assert isinstance(trig, CronTrigger)
    # 2026-04-25 is a Saturday → next Monday is 2026-04-27 09:00 UTC.
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 25, tzinfo=UTC))
    assert fire == datetime(2026, 4, 27, 9, 0, tzinfo=UTC)


def test_recurring_multiple_hours_uses_or_trigger():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {
            "type": "recurring",
            "days": ["mon"],
            "hours": ["09:00", "17:30"],
        },
    })
    trig = to_trigger(sd, default_zone=UTC)
    assert isinstance(trig, OrTrigger)
    after_morning = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)  # Mon afternoon
    fire = trig.get_next_fire_time(None, after_morning)
    assert fire == datetime(2026, 4, 27, 17, 30, tzinfo=UTC)


def test_recurring_does_not_collapse_cross_product():
    """09:30 + 17:00 must NOT fire 09:00, 17:30 — that was the cron pitfall
    the OrTrigger composition exists to avoid."""
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {
            "type": "recurring",
            "days": ["mon"],
            "hours": ["09:30", "17:00"],
        },
    })
    trig = to_trigger(sd, default_zone=UTC)
    base = datetime(2026, 4, 27, 0, 0, tzinfo=UTC)
    fires: list[datetime] = []
    cur = base
    for _ in range(4):
        cur = trig.get_next_fire_time(None, cur)
        if cur is None:
            break
        fires.append(cur)
        cur = cur.replace(minute=cur.minute + 1)
    assert fires[0] == datetime(2026, 4, 27, 9, 30, tzinfo=UTC)
    assert fires[1] == datetime(2026, 4, 27, 17, 0, tzinfo=UTC)
    # No spurious 09:00 or 17:30 fires.
    bad_minutes = {(d.hour, d.minute) for d in fires} & {(9, 0), (17, 30)}
    assert not bad_minutes


def test_recurring_per_schedule_timezone():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "timezone": "America/New_York",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    trig = to_trigger(sd, default_zone=UTC)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 25, tzinfo=UTC))
    # 09:00 NYC on the next Monday = 13:00 UTC (EDT, -4)
    assert fire.astimezone(NYC) == datetime(2026, 4, 27, 9, 0, tzinfo=NYC)


def test_recurring_daily():
    sd = _def({
        "name": "x",
        "conduit": "c",
        "schedule": {"type": "recurring", "days": ["*"], "hours": ["00:00"]},
    })
    trig = to_trigger(sd, default_zone=UTC)
    fire = trig.get_next_fire_time(
        None, datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    )
    assert fire == datetime(2026, 4, 26, 0, 0, tzinfo=UTC)


# -------------------------------------------------------------- default zone


def test_default_local_zone_returns_zoneinfo():
    z = default_local_zone()
    assert isinstance(z, ZoneInfo)
