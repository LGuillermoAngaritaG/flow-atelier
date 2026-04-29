"""Schedule definition schemas (YAML-driven scheduler)."""
from __future__ import annotations

import re
from datetime import datetime, time
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


_DAY_ALIASES: dict[str, str] = {
    "0": "mon", "1": "tue", "2": "wed", "3": "thu",
    "4": "fri", "5": "sat", "6": "sun",
    "mon": "mon", "monday": "mon",
    "tue": "tue", "tues": "tue", "tuesday": "tue",
    "wed": "wed", "weds": "wed", "wednesday": "wed",
    "thu": "thu", "thurs": "thu", "thursday": "thu",
    "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
    "*": "*", "daily": "*", "all": "*", "any": "*", "everyday": "*",
}

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")

DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class _ScheduleBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OnceSchedule(_ScheduleBase):
    """Fire exactly once at the given instant."""

    type: Literal["once"]
    at: datetime

    @field_validator("at", mode="before")
    @classmethod
    def _parse_iso(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(f"invalid ISO 8601 datetime: {v!r}") from e
        return v


class RecurringSchedule(_ScheduleBase):
    """Fire on every (day-of-week × time-of-day) cross product."""

    type: Literal["recurring"]
    days: list[str] = Field(min_length=1)
    hours: list[time] = Field(min_length=1)

    @field_validator("days", mode="before")
    @classmethod
    def _normalize_days(cls, v: Any) -> Any:
        if not isinstance(v, list):
            raise ValueError("days must be a list")
        if not v:
            raise ValueError("days must contain at least one entry")
        out: list[str] = []
        seen: set[str] = set()
        for item in v:
            if not isinstance(item, (str, int)):
                raise ValueError(f"day must be a string or 0-6 int: {item!r}")
            key = str(item).strip().lower()
            if key not in _DAY_ALIASES:
                raise ValueError(
                    f"unknown day {item!r}; allowed: mon..sun, monday..sunday, 0-6, '*'"
                )
            normalized = _DAY_ALIASES[key]
            if normalized == "*":
                return DAY_ORDER.copy()
            if normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
        out.sort(key=DAY_ORDER.index)
        return out

    @field_validator("hours", mode="before")
    @classmethod
    def _parse_hours(cls, v: Any) -> Any:
        if not isinstance(v, list):
            raise ValueError("hours must be a list")
        if not v:
            raise ValueError("hours must contain at least one entry")
        out: list[time] = []
        seen: set[str] = set()
        for item in v:
            if isinstance(item, time):
                t = item
            elif isinstance(item, str):
                m = _HHMM_RE.match(item.strip())
                if not m:
                    raise ValueError(
                        f"invalid time-of-day {item!r}; expected 'HH:MM' (00-23:00-59)"
                    )
                hour = int(m.group(1))
                minute = int(m.group(2))
                second = int(m.group(3)) if m.group(3) is not None else 0
                t = time(hour, minute, second)
            else:
                raise ValueError(f"hour must be a 'HH:MM' string: {item!r}")
            key = t.isoformat()
            if key not in seen:
                seen.add(key)
                out.append(t)
        out.sort()
        return out

    @field_serializer("hours")
    def _serialize_hours(self, value: list[time]) -> list[str]:
        return [t.strftime("%H:%M") if t.second == 0 else t.strftime("%H:%M:%S") for t in value]


ScheduleSpec = Annotated[
    OnceSchedule | RecurringSchedule,
    Field(discriminator="type"),
]


class ScheduleDefinition(BaseModel):
    """Top-level schedule entry parsed from ``.atelier/schedules/<name>.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    conduit: str
    working_dir: Path | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    timezone: str | None = None
    schedule: ScheduleSpec

    @field_validator("name", "conduit")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("timezone")
    @classmethod
    def _validate_tz(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone {v!r}: {e}") from e
        return v

    def resolve_zone(self, default: ZoneInfo) -> ZoneInfo:
        """Return the IANA zone for this schedule, falling back to ``default``."""
        return ZoneInfo(self.timezone) if self.timezone else default
