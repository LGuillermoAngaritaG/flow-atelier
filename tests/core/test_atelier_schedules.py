"""Atelier facade: schedule CRUD."""
from __future__ import annotations

import pytest

from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput, ScheduledJob


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    """Construct an Atelier instance rooted under tmp_path.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


def _payload(**overrides) -> CreateScheduleInput:
    """Build a CreateScheduleInput payload with overrides applied.

    :param overrides: keyword overrides merged into the base payload.
    """
    base = {
        "conduit_name": "report",
        "inputs": {"foo": "bar"},
        "run_path": "/tmp/x",
        "schedule": {
            "mode": "recurring",
            "name": "weekday mornings",
            "days": [1, 2, 3, 4, 5],
            "times": ["06:00"],
        },
    }
    base.update(overrides)
    return CreateScheduleInput.model_validate(base)


def test_list_schedules_starts_empty(atelier):
    """Verify list_schedules returns [] for a fresh Atelier.

    :param atelier: Atelier facade fixture.
    """
    assert atelier.list_schedules() == []


def test_create_schedule_returns_scheduled_job(atelier):
    """Verify create_schedule returns a ScheduledJob with a SCH- id.

    :param atelier: Atelier facade fixture.
    """
    job = atelier.create_schedule(_payload())
    assert isinstance(job, ScheduledJob)
    assert job.conduit_name == "report"
    assert job.id.startswith("SCH-")


def test_list_schedules_includes_created(atelier):
    """Verify list_schedules includes a freshly created schedule.

    :param atelier: Atelier facade fixture.
    """
    job = atelier.create_schedule(_payload())
    listed = atelier.list_schedules()
    assert [j.id for j in listed] == [job.id]


def test_delete_schedule_removes_from_list(atelier):
    """Verify delete_schedule hard-deletes and drops the schedule from list.

    :param atelier: Atelier facade fixture.
    """
    job = atelier.create_schedule(_payload())
    deleted = atelier.delete_schedule(job.id)
    assert deleted.id == job.id
    assert atelier.list_schedules() == []


def test_delete_schedule_unknown_raises_keyerror(atelier):
    """Verify delete_schedule raises KeyError for an unknown id.

    :param atelier: Atelier facade fixture.
    """
    with pytest.raises(KeyError):
        atelier.delete_schedule("SCH-nope")
