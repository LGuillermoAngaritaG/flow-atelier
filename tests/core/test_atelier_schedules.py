"""Atelier facade: schedule CRUD."""
from __future__ import annotations

import pytest

from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput, ScheduledJob


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


def _payload(**overrides) -> CreateScheduleInput:
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
    assert atelier.list_schedules() == []


def test_create_schedule_returns_scheduled_job(atelier):
    job = atelier.create_schedule(_payload())
    assert isinstance(job, ScheduledJob)
    assert job.conduit_name == "report"
    assert job.id.startswith("SCH-")


def test_list_schedules_includes_created(atelier):
    job = atelier.create_schedule(_payload())
    listed = atelier.list_schedules()
    assert [j.id for j in listed] == [job.id]


def test_delete_schedule_soft_deletes(atelier):
    job = atelier.create_schedule(_payload())
    deleted = atelier.delete_schedule(job.id)
    assert deleted.status == "deleted"
    assert atelier.list_schedules() == []


def test_delete_schedule_unknown_raises_keyerror(atelier):
    with pytest.raises(KeyError):
        atelier.delete_schedule("SCH-nope")
