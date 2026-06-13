"""Tests for the YAML-backed ScheduleStore."""
from __future__ import annotations

import pytest
import yaml

from flow_atelier.schemas.api import CreateScheduleInput
from flow_atelier.services.scheduler.store import ScheduleStore

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
            "run_at": "2099-05-01T09:00:00Z",
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


def test_create_assigns_id_created_at_counters(store):
    """Verify create() assigns id, created_at, and counters.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    assert job.id.startswith("SCH-")
    assert job.runs_completed == 0
    assert job.created_at > 0
    assert job.conduit_name == "report"


def test_create_persists_to_yaml_file(store):
    """Verify create() persists the schedule into a per-name YAML file.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    (yaml_path,) = list(store.schedules_dir.glob("weekday-mornings-*.yaml"))
    assert yaml_path.exists()
    raw = yaml.safe_load(yaml_path.read_text())
    assert raw["id"] == job.id
    assert raw["conduit_name"] == "report"
    assert raw["schedule"]["mode"] == "recurring"
    assert raw["schedule"]["name"] == "weekday mornings"


def test_filename_is_slugified(store):
    """Verify the filename keeps a lowercase slug of ``schedule.name`` as a
    readable prefix (a disambiguating hash is appended).

    :param store: ScheduleStore fixture.
    """
    store.create(_recurring_payload(schedule={
        "mode": "recurring",
        "name": "Weekday Mornings!",
        "days": [1], "times": ["06:00"],
    }))
    files = list(store.schedules_dir.glob("weekday-mornings-*.yaml"))
    assert len(files) == 1


def test_distinct_names_same_slug_dont_collide(store):
    """Two names that slug identically map to two distinct files, each
    retrievable by its own name and id; an exact-duplicate name still raises.

    :param store: ScheduleStore fixture.
    """
    a = store.create(_recurring_payload(schedule={
        "mode": "recurring", "name": "My Job", "days": [1], "times": ["06:00"],
    }))
    b = store.create(_recurring_payload(schedule={
        "mode": "recurring", "name": "my-job", "days": [1], "times": ["06:00"],
    }))
    assert len(list(store.schedules_dir.glob("*.yaml"))) == 2
    assert a.id != b.id
    assert store.get_by_name("My Job").id == a.id
    assert store.get_by_name("my-job").id == b.id
    assert store.get(a.id).id == a.id
    assert store.get(b.id).id == b.id
    # Exact-duplicate name still collides on one file.
    with pytest.raises(FileExistsError):
        store.create(_recurring_payload(schedule={
            "mode": "recurring", "name": "My Job", "days": [1], "times": ["06:00"],
        }))


def test_create_rejects_empty_name(store):
    """Verify create() rejects an empty schedule.name.

    :param store: ScheduleStore fixture.
    """
    with pytest.raises(ValueError):
        store.create(_once_payload(schedule={
            "mode": "once", "name": "", "run_at": "2099-05-01T09:00:00Z",
        }))


def test_create_rejects_duplicate_slug(store):
    """Verify create() refuses to overwrite an existing schedule slug.

    :param store: ScheduleStore fixture.
    """
    store.create(_recurring_payload())
    with pytest.raises(FileExistsError):
        store.create(_recurring_payload())


def test_list_drops_deleted_schedules(store):
    """Verify list() no longer surfaces a schedule whose file was deleted.

    :param store: ScheduleStore fixture.
    """
    a = store.create(_recurring_payload())
    b = store.create(_once_payload())
    listed = store.list()
    ids = [j.id for j in listed]
    assert a.id in ids and b.id in ids
    store.delete(a.id)
    listed_after = store.list()
    assert a.id not in [j.id for j in listed_after]
    assert b.id in [j.id for j in listed_after]


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
    (path,) = list(store.schedules_dir.glob("weekday-mornings-*.yaml"))
    assert path.exists()
    deleted = store.delete(job.id)
    assert deleted.id == job.id
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


def test_increment_runs_skips_when_file_gone(store):
    """The delete-then-increment race: once a job's YAML file is unlinked,
    ``increment_runs`` must NOT resurrect it.

    :param store: ScheduleStore fixture.
    """
    job = store.create(_recurring_payload())
    (path,) = list(store.schedules_dir.glob("*.yaml"))
    path.unlink()
    store.increment_runs(job.id)
    assert not path.exists()
    assert list(store.schedules_dir.glob("*.yaml")) == []


def test_union_reads_project_and_global(tmp_path):
    """A schedule living in the global dir is visible alongside project ones.

    Mirrors the CLI(project)↔serve(global) split-brain fix: reads union both
    dirs while writes stay project-local.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / "project" / ".atelier"
    global_dir = tmp_path / "global" / ".atelier"
    # A schedule installed against the *global* dir (e.g. by a previous serve).
    ScheduleStore(global_dir).create(
        _recurring_payload(schedule={
            "mode": "recurring", "name": "global job",
            "days": [1], "times": ["06:00"],
        })
    )
    store = ScheduleStore(project, global_dir=global_dir)
    proj_job = store.create(_recurring_payload(schedule={
        "mode": "recurring", "name": "project job",
        "days": [2], "times": ["07:00"],
    }))
    names = {j.schedule.name for j in store.list()}
    assert names == {"global job", "project job"}
    # Writes land in the project dir, never the global dir.
    assert list((project / "schedules").glob("project-job-*.yaml"))
    assert not list((global_dir / "schedules").glob("project-job-*.yaml"))
    # Project-side store can still find/delete the project job.
    assert store.get(proj_job.id).id == proj_job.id


def test_find_and_delete_reach_global_schedule(tmp_path):
    """get/delete locate a schedule that physically lives in the global dir.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / "project" / ".atelier"
    global_dir = tmp_path / "global" / ".atelier"
    global_job = ScheduleStore(global_dir).create(_recurring_payload())
    store = ScheduleStore(project, global_dir=global_dir)
    assert store.get(global_job.id) is not None
    store.delete(global_job.id)
    assert store.get(global_job.id) is None


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
