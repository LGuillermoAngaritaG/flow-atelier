"""Tests for the YAML-backed ScheduleStore."""
from __future__ import annotations

import pytest
import yaml

from app.schemas.api import CreateScheduleInput
from app.services.scheduler.store import ScheduleStore

# ----------------------------------------------------------- fixtures / helpers


@pytest.fixture
def store(tmp_path) -> ScheduleStore:
    """Provide a ScheduleStore rooted at a temp .atelier directory.

    :param tmp_path: pytest temp directory fixture.
    """
    return ScheduleStore(tmp_path / ".atelier")


def _recurring_payload(**overrides):
    """Build a recurring CreateScheduleInput with optional overrides.

    :param overrides: keyword overrides applied to the base payload.
    """
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
    """Build a once-mode CreateScheduleInput with optional overrides.

    :param overrides: keyword overrides applied to the base payload.
    """
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
    """Verify an empty store returns no schedules.

    :param store: ScheduleStore fixture.
    """
    assert store.list() == []


def test_create_assigns_id_created_at_status(store):
    """Verify create() assigns id, created_at, status, and counters.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    assert job.id.startswith("SCH-")
    assert job.status == "active"
    assert job.runs_completed == 0
    assert job.created_at > 0
    assert job.conduit_name == "report"


def test_create_persists_to_yaml_file(store):
    """Verify create() persists the schedule into a per-name YAML file.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    yaml_path = store.schedules_dir / "weekday-mornings.yaml"
    assert yaml_path.exists()
    raw = yaml.safe_load(yaml_path.read_text())
    assert raw["id"] == job.id
    assert raw["conduit_name"] == "report"
    assert raw["schedule"]["mode"] == "recurring"
    assert raw["schedule"]["name"] == "weekday mornings"


def test_filename_is_slugified(store):
    """Verify the filename is a lowercase slug of ``schedule.name``.

    :param store: ScheduleStore fixture.
    """
    store.create(_recurring_payload(schedule={
        "mode": "recurring",
        "name": "Weekday Mornings!",
        "days": [1], "times": ["06:00"],
    }))
    assert (store.schedules_dir / "weekday-mornings.yaml").exists()


def test_create_rejects_empty_name(store):
    """Verify create() rejects an empty schedule.name.

    :param store: ScheduleStore fixture.
    """
    with pytest.raises(ValueError):
        store.create(_once_payload(schedule={
            "mode": "once", "name": "", "run_at": "2026-05-01T09:00:00Z",
        }))


def test_create_rejects_duplicate_slug(store):
    """Verify create() refuses to overwrite an existing schedule slug.

    :param store: ScheduleStore fixture.
    """
    store.create(_recurring_payload())
    with pytest.raises(FileExistsError):
        store.create(_recurring_payload())


def test_list_returns_active_schedules_only(store):
    """Verify list() excludes deleted schedules.

    :param store: ScheduleStore fixture.
    """
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
    """Verify get() returns the schedule matching the id.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    again = store.get(job.id)
    assert again is not None
    assert again.id == job.id


def test_get_unknown_returns_none(store):
    """Verify get() returns None for unknown ids.

    :param store: ScheduleStore fixture.
    """
    assert store.get("SCH-nope") is None


# ----------------------------------------------------------- delete (hard)


def test_delete_removes_file(store):
    """Verify delete() removes the schedule's YAML file.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    path = store.schedules_dir / "weekday-mornings.yaml"
    assert path.exists()
    deleted = store.delete(job.id)
    assert deleted.status == "deleted"
    assert not path.exists()


def test_delete_unknown_raises(store):
    """Verify delete() raises KeyError for unknown ids.

    :param store: ScheduleStore fixture.
    """
    with pytest.raises(KeyError):
        store.delete("SCH-nope")


def test_delete_clears_fired_state(store):
    """Verify delete() clears any persisted fired-state marker.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_once_payload())
    store.mark_fired(job.id)
    assert store.fired_at(job.id) is not None
    store.delete(job.id)
    assert store.fired_at(job.id) is None


# ----------------------------------------------------------- fired-state


def test_fired_state_round_trip(store):
    """Verify mark_fired and fired_at round-trip the timestamp.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_once_payload())
    assert store.fired_at(job.id) is None
    store.mark_fired(job.id)
    assert store.fired_at(job.id) is not None


def test_clear_fired_removes_marker(store):
    """Verify clear_fired removes the previously-stored marker.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_once_payload())
    store.mark_fired(job.id)
    store.clear_fired(job.id)
    assert store.fired_at(job.id) is None


def test_state_resilient_to_corrupt_file(store):
    """Verify state methods tolerate a corrupt state file.

    :param store: ScheduleStore fixture.
    """
    store.state_path.parent.mkdir(parents=True, exist_ok=True)
    store.state_path.write_text("{not json")
    assert store.fired_at("SCH-x") is None
    store.mark_fired("SCH-x")
    assert store.fired_at("SCH-x") is not None


# ----------------------------------------------------------- atomic write


def test_atomic_write_does_not_leave_tmp(store):
    """Verify atomic writes do not leave temp files behind.

    :param store: ScheduleStore fixture.
    """
    store.create(_recurring_payload())
    leftovers = list(store.schedules_dir.glob("*.yaml.tmp"))
    assert leftovers == []


def test_recreate_after_load_round_trips(store, tmp_path):
    """Verify a fresh ScheduleStore reloads previously persisted data.

    :param store: ScheduleStore fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    job = store.create(_recurring_payload())
    fresh = ScheduleStore(tmp_path / ".atelier")
    listed = fresh.list()
    assert len(listed) == 1
    assert listed[0].id == job.id
    assert listed[0].schedule.times == ["06:00", "12:00"]
