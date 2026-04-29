"""Tests for trigger construction (APScheduler integration, JSON store)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.schemas.api import ScheduledJob
from app.services.scheduler.triggers import default_local_zone, to_trigger


UTC = ZoneInfo("UTC")
NYC = ZoneInfo("America/New_York")


def _job(schedule: dict, **overrides) -> ScheduledJob:
    base = {
        "id": "SCH-test",
        "conduit_name": "c",
        "inputs": {},
        "run_path": "/tmp",
        "schedule": schedule,
        "created_at": 0,
        "status": "active",
        "runs_completed": 0,
    }
    base.update(overrides)
    return ScheduledJob.model_validate(base)


# -------------------------------------------------------------- once


def test_once_aware_run_at_uses_explicit_tz():
    job = _job({"mode": "once", "name": "x", "run_at": "2026-05-01T09:00:00Z"})
    trig = to_trigger(job, default_zone=NYC)
    assert isinstance(trig, DateTrigger)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 1, tzinfo=UTC))
    assert fire == datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)


def test_once_naive_run_at_uses_default_zone():
    job = _job({"mode": "once", "name": "x", "run_at": "2026-05-01T09:00:00"})
    trig = to_trigger(job, default_zone=UTC)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 1, tzinfo=UTC))
    assert fire == datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


# -------------------------------------------------------------- recurring


def test_recurring_single_time_returns_cron():
    job = _job(
        {
            "mode": "recurring",
            "name": "x",
            "days": [1],  # Monday
            "times": ["09:00"],
        }
    )
    trig = to_trigger(job, default_zone=UTC)
    assert isinstance(trig, CronTrigger)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 25, tzinfo=UTC))
    assert fire == datetime(2026, 4, 27, 9, 0, tzinfo=UTC)


def test_recurring_multiple_times_uses_or_trigger():
    job = _job(
        {
            "mode": "recurring",
            "name": "x",
            "days": [1],
            "times": ["09:00", "17:30"],
        }
    )
    trig = to_trigger(job, default_zone=UTC)
    assert isinstance(trig, OrTrigger)
    after_morning = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    fire = trig.get_next_fire_time(None, after_morning)
    assert fire == datetime(2026, 4, 27, 17, 30, tzinfo=UTC)


def test_recurring_does_not_collapse_cross_product():
    job = _job(
        {
            "mode": "recurring",
            "name": "x",
            "days": [1],
            "times": ["09:30", "17:00"],
        }
    )
    trig = to_trigger(job, default_zone=UTC)
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
    bad_minutes = {(d.hour, d.minute) for d in fires} & {(9, 0), (17, 30)}
    assert not bad_minutes


def test_recurring_full_week():
    job = _job(
        {
            "mode": "recurring",
            "name": "x",
            "days": [1, 2, 3, 4, 5, 6, 7],
            "times": ["00:00"],
        }
    )
    trig = to_trigger(job, default_zone=UTC)
    fire = trig.get_next_fire_time(None, datetime(2026, 4, 25, 12, 0, tzinfo=UTC))
    assert fire == datetime(2026, 4, 26, 0, 0, tzinfo=UTC)


def test_default_local_zone_returns_zoneinfo():
    z = default_local_zone()
    assert isinstance(z, ZoneInfo)
