"""Tests for the JSON-backed ScheduleStore (per SPEC §7)."""
from __future__ import annotations

import json

import pytest

from app.schemas.api import CreateScheduleInput
from app.services.scheduler.store import ScheduleStore


# ----------------------------------------------------------- fixtures / helpers


@pytest.fixture
def store(tmp_path) -> ScheduleStore:
    return ScheduleStore(tmp_path / ".atelier")


def _recurring_payload(**overrides):
    base = {
        "conduit_name": "report",
        "inputs": {"foo": "bar"},
        "run_path": "/tmp/x",
        "schedule": {
            "mode": "recurring",
            "name": "weekday mornings",
            "days": [1, 2, 3, 4, 5],
            "times": ["06:00", "12:00"],
        },
    }
    base.update(overrides)
    return CreateScheduleInput.model_validate(base)


def _once_payload(**overrides):
    base = {
        "conduit_name": "backfill",
        "inputs": {},
        "run_path": "/tmp/x",
        "schedule": {
            "mode": "once",
            "name": "tomorrow",
            "run_at": "2026-05-01T09:00:00Z",
        },
    }
    base.update(overrides)
    return CreateScheduleInput.model_validate(base)


# ----------------------------------------------------------- list / create


def test_list_empty(store):
    assert store.list() == []


def test_create_assigns_id_created_at_status(store):
    job = store.create(_recurring_payload())
    assert job.id.startswith("SCH-")
    assert job.status == "active"
    assert job.runs_completed == 0
    assert job.created_at > 0
    assert job.conduit_name == "report"


def test_create_persists_to_schedules_json(store):
    job = store.create(_recurring_payload())
    raw = json.loads(store.schedules_path.read_text())
    assert "schedules" in raw
    assert raw["schedules"][0]["id"] == job.id
    assert raw["schedules"][0]["conduit_name"] == "report"
    assert raw["schedules"][0]["schedule"]["mode"] == "recurring"


def test_list_returns_active_schedules_only(store):
    a = store.create(_recurring_payload())
    b = store.create(_once_payload())
    listed = store.list()
    ids = [j.id for j in listed]
    assert a.id in ids and b.id in ids
    store.delete(a.id)
    listed_after = store.list()
    assert all(j.status == "active" for j in listed_after)
    assert a.id not in [j.id for j in listed_after]


def test_get_by_id(store):
    job = store.create(_recurring_payload())
    again = store.get(job.id)
    assert again is not None
    assert again.id == job.id


def test_get_unknown_returns_none(store):
    assert store.get("SCH-nope") is None


# ----------------------------------------------------------- delete (soft)


def test_delete_marks_status_deleted(store):
    job = store.create(_recurring_payload())
    deleted = store.delete(job.id)
    assert deleted.status == "deleted"
    # Soft delete: still present in raw file
    raw = json.loads(store.schedules_path.read_text())
    statuses = [s["status"] for s in raw["schedules"]]
    assert "deleted" in statuses


def test_delete_unknown_raises(store):
    with pytest.raises(KeyError):
        store.delete("SCH-nope")


def test_delete_clears_fired_state(store):
    job = store.create(_once_payload())
    store.mark_fired(job.id)
    assert store.fired_at(job.id) is not None
    store.delete(job.id)
    assert store.fired_at(job.id) is None


# ----------------------------------------------------------- fired-state


def test_fired_state_round_trip(store):
    job = store.create(_once_payload())
    assert store.fired_at(job.id) is None
    store.mark_fired(job.id)
    assert store.fired_at(job.id) is not None


def test_clear_fired_removes_marker(store):
    job = store.create(_once_payload())
    store.mark_fired(job.id)
    store.clear_fired(job.id)
    assert store.fired_at(job.id) is None


def test_state_resilient_to_corrupt_file(store):
    store.state_path.parent.mkdir(parents=True, exist_ok=True)
    store.state_path.write_text("{not json")
    assert store.fired_at("SCH-x") is None
    store.mark_fired("SCH-x")
    assert store.fired_at("SCH-x") is not None


# ----------------------------------------------------------- atomic write


def test_atomic_write_does_not_leave_tmp(store):
    store.create(_recurring_payload())
    leftovers = list(store.atelier_dir.glob("schedules.json.tmp"))
    assert leftovers == []


def test_recreate_after_load_round_trips(store, tmp_path):
    job = store.create(_recurring_payload())
    fresh = ScheduleStore(tmp_path / ".atelier")
    listed = fresh.list()
    assert len(listed) == 1
    assert listed[0].id == job.id
    assert listed[0].schedule.times == ["06:00", "12:00"]
