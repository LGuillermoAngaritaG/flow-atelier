"""Schedule schema validation tests."""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.schemas.schedule import (
    DAY_ORDER,
    OnceSchedule,
    RecurringSchedule,
    ScheduleDefinition,
)


def _recurring_payload(**overrides):
    base = {
        "name": "nightly",
        "conduit": "report",
        "schedule": {
            "type": "recurring",
            "days": ["mon", "wed", "fri"],
            "hours": ["09:00", "17:30"],
        },
    }
    base.update(overrides)
    return base


def _once_payload(**overrides):
    base = {
        "name": "backfill",
        "conduit": "backfill",
        "schedule": {"type": "once", "at": "2026-05-01T09:00:00"},
    }
    base.update(overrides)
    return base


# -------------------------------------------------------------- happy paths


def test_recurring_basic():
    sd = ScheduleDefinition.model_validate(_recurring_payload())
    assert isinstance(sd.schedule, RecurringSchedule)
    assert sd.schedule.days == ["mon", "wed", "fri"]
    assert sd.schedule.hours == [time(9, 0), time(17, 30)]


def test_once_basic():
    sd = ScheduleDefinition.model_validate(_once_payload())
    assert isinstance(sd.schedule, OnceSchedule)
    assert sd.schedule.at == datetime(2026, 5, 1, 9, 0)


def test_once_z_suffix_parses_as_utc():
    sd = ScheduleDefinition.model_validate(
        _once_payload(schedule={"type": "once", "at": "2026-05-01T09:00:00Z"})
    )
    assert sd.schedule.at == datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)


# -------------------------------------------------------------- day normalization


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["MON", "Wed"], ["mon", "wed"]),
        (["monday", "Tuesday"], ["mon", "tue"]),
        (["fri", "fri", "tue"], ["tue", "fri"]),
        (["0", 6], ["mon", "sun"]),
        (["*"], DAY_ORDER),
        (["daily"], DAY_ORDER),
        (["any", "mon"], DAY_ORDER),
    ],
)
def test_day_normalization(raw, expected):
    sd = ScheduleDefinition.model_validate(
        _recurring_payload(schedule={"type": "recurring", "days": raw, "hours": ["08:00"]})
    )
    assert sd.schedule.days == expected


def test_day_unknown_rejected():
    with pytest.raises(ValidationError) as exc:
        ScheduleDefinition.model_validate(
            _recurring_payload(
                schedule={"type": "recurring", "days": ["funday"], "hours": ["08:00"]}
            )
        )
    assert "unknown day" in str(exc.value)


# -------------------------------------------------------------- hour parsing


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["08:00"], [time(8, 0)]),
        (["8:00"], [time(8, 0)]),
        (["23:59"], [time(23, 59)]),
        (["09:30", "09:30", "08:00"], [time(8, 0), time(9, 30)]),
    ],
)
def test_hour_parsing(raw, expected):
    sd = ScheduleDefinition.model_validate(
        _recurring_payload(schedule={"type": "recurring", "days": ["mon"], "hours": raw})
    )
    assert sd.schedule.hours == expected


@pytest.mark.parametrize(
    "bad",
    ["24:00", "9", "9:0", "noon", "9:60", "-1:00"],
)
def test_hour_invalid_rejected(bad):
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(
            _recurring_payload(
                schedule={"type": "recurring", "days": ["mon"], "hours": [bad]}
            )
        )


def test_hours_must_not_be_empty():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(
            _recurring_payload(
                schedule={"type": "recurring", "days": ["mon"], "hours": []}
            )
        )


def test_days_must_not_be_empty():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(
            _recurring_payload(
                schedule={"type": "recurring", "days": [], "hours": ["08:00"]}
            )
        )


# -------------------------------------------------------------- timezone


def test_timezone_valid():
    sd = ScheduleDefinition.model_validate(
        _recurring_payload(timezone="America/Bogota")
    )
    assert sd.timezone == "America/Bogota"
    assert sd.resolve_zone(ZoneInfo("UTC")) == ZoneInfo("America/Bogota")


def test_timezone_unknown_rejected():
    with pytest.raises(ValidationError) as exc:
        ScheduleDefinition.model_validate(_recurring_payload(timezone="Mars/Olympus"))
    assert "unknown timezone" in str(exc.value)


def test_timezone_default_resolution_uses_fallback():
    sd = ScheduleDefinition.model_validate(_recurring_payload())
    assert sd.timezone is None
    assert sd.resolve_zone(ZoneInfo("UTC")) == ZoneInfo("UTC")


# -------------------------------------------------------------- discriminator


def test_unknown_schedule_type_rejected():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(
            _once_payload(schedule={"type": "weekly", "at": "2026-01-01T00:00:00"})
        )


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(_recurring_payload(extra="nope"))


def test_once_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(
            _once_payload(
                schedule={
                    "type": "once",
                    "at": "2026-05-01T09:00:00",
                    "days": ["mon"],
                }
            )
        )


# -------------------------------------------------------------- name/conduit


def test_name_strips_whitespace():
    sd = ScheduleDefinition.model_validate(_recurring_payload(name="  nightly  "))
    assert sd.name == "nightly"


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        ScheduleDefinition.model_validate(_recurring_payload(name="   "))


def test_inputs_default_empty_dict():
    sd = ScheduleDefinition.model_validate(_recurring_payload())
    assert sd.inputs == {}


def test_inputs_arbitrary_values():
    sd = ScheduleDefinition.model_validate(
        _recurring_payload(inputs={"date": "today", "n": 3, "flag": True})
    )
    assert sd.inputs == {"date": "today", "n": 3, "flag": True}
