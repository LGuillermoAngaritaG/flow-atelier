"""Tests for ScheduleStore: YAML CRUD and fired-state persistence."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from app.schemas.schedule import ScheduleDefinition
from app.services.scheduler.store import ScheduleStore


RECURRING_YAML = """
conduit: report
inputs:
  date: today
schedule:
  type: recurring
  days: [mon, fri]
  hours: ["09:00"]
"""

ONCE_YAML = """
conduit: backfill
schedule:
  type: once
  at: "2026-05-01T09:00:00"
"""


@pytest.fixture
def store(tmp_path) -> ScheduleStore:
    return ScheduleStore(tmp_path / "schedules")


def _write(store: ScheduleStore, name: str, body: str) -> Path:
    p = store.path_for(name)
    p.write_text(body)
    return p


# -------------------------------------------------------------- list / read


def test_list_empty(store):
    assert store.list_definitions() == []


def test_list_picks_up_yaml_and_yml(store):
    _write(store, "a", RECURRING_YAML)
    (store.schedules_dir / "b.yml").write_text(ONCE_YAML)
    loaded = store.list_definitions()
    names = [ls.definition.name for ls in loaded]
    assert names == ["a", "b"]


def test_list_skips_dotfiles(store):
    _write(store, "a", RECURRING_YAML)
    (store.schedules_dir / ".state.json").write_text("{}")
    (store.schedules_dir / ".hidden.yaml").write_text(RECURRING_YAML)
    names = [ls.definition.name for ls in store.list_definitions()]
    assert names == ["a"]


def test_list_records_errors_for_broken_yaml(store):
    _write(store, "good", RECURRING_YAML)
    _write(store, "broken", "name: broken\n  bad: indentation")
    loaded, errors = store.list_definitions_with_errors()
    assert [ls.definition.name for ls in loaded] == ["good"]
    assert len(errors) == 1
    assert errors[0].source_path.name == "broken.yaml"


def test_list_records_errors_for_invalid_schema(store):
    _write(store, "bad", textwrap.dedent("""
        conduit: x
        schedule:
          type: recurring
          days: [funday]
          hours: ["09:00"]
    """))
    loaded, errors = store.list_definitions_with_errors()
    assert loaded == []
    assert len(errors) == 1


def test_read_unknown(store):
    with pytest.raises(FileNotFoundError):
        store.read("missing")


def test_read_patches_name_from_filename(store):
    _write(store, "weekly", RECURRING_YAML)
    sd = store.read("weekly")
    assert sd.name == "weekly"


def test_read_rejects_filename_name_mismatch(store):
    _write(store, "weekly", "name: other\n" + RECURRING_YAML)
    with pytest.raises(ValueError) as exc:
        store.read("weekly")
    assert "filename stem" in str(exc.value)


# -------------------------------------------------------------- write


def test_write_creates_file_and_omits_name_field(store):
    sd = ScheduleDefinition.model_validate({
        "name": "nightly",
        "conduit": "report",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    path = store.write(sd)
    assert path.exists()
    raw = yaml.safe_load(path.read_text())
    assert "name" not in raw
    assert raw["conduit"] == "report"
    # Round-trip via read.
    parsed = store.read("nightly")
    assert parsed.name == "nightly"
    assert parsed.conduit == "report"


def test_write_collision_without_force(store):
    sd = ScheduleDefinition.model_validate({
        "name": "n",
        "conduit": "c",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    store.write(sd)
    with pytest.raises(FileExistsError):
        store.write(sd)


def test_write_force_overwrites(store):
    sd = ScheduleDefinition.model_validate({
        "name": "n",
        "conduit": "old",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    store.write(sd)
    sd2 = ScheduleDefinition.model_validate({
        "name": "n",
        "conduit": "new",
        "schedule": {"type": "recurring", "days": ["mon"], "hours": ["09:00"]},
    })
    store.write(sd2, force=True)
    assert store.read("n").conduit == "new"


# -------------------------------------------------------------- install


def test_install_copies_file(tmp_path, store):
    src = tmp_path / "scratch.yaml"
    src.write_text("name: copied\n" + RECURRING_YAML)
    dest = store.install(src)
    assert dest == store.path_for("copied")
    assert store.read("copied").conduit == "report"


def test_install_uses_filename_when_no_name_field(tmp_path, store):
    src = tmp_path / "from-stem.yaml"
    src.write_text(RECURRING_YAML)
    dest = store.install(src)
    assert dest.name == "from-stem.yaml"


def test_install_rejects_collision(tmp_path, store):
    src = tmp_path / "scratch.yaml"
    src.write_text("name: dup\n" + RECURRING_YAML)
    store.install(src)
    with pytest.raises(FileExistsError):
        store.install(src)


def test_install_force_overwrites(tmp_path, store):
    src = tmp_path / "scratch.yaml"
    src.write_text("name: dup\n" + RECURRING_YAML)
    store.install(src)
    src.write_text("name: dup\nconduit: changed\nschedule:\n  type: once\n  at: '2026-01-01T00:00:00'\n")
    store.install(src, force=True)
    assert store.read("dup").conduit == "changed"


def test_install_validates_before_writing(tmp_path, store):
    src = tmp_path / "bad.yaml"
    src.write_text("name: bad\nconduit: c\nschedule:\n  type: bogus\n")
    with pytest.raises(Exception):  # ValidationError surfaces as ValueError-like
        store.install(src)
    assert not store.path_for("bad").exists()


# -------------------------------------------------------------- remove


def test_remove_returns_true_when_existed(store):
    _write(store, "x", RECURRING_YAML)
    store.mark_fired("x", "2026-05-01T09:00:00")
    assert store.remove("x") is True
    assert not store.path_for("x").exists()
    assert store.fired_at("x") is None


def test_remove_returns_false_when_missing(store):
    assert store.remove("ghost") is False


# -------------------------------------------------------------- fired-state


def test_fired_state_round_trip(store):
    assert store.fired_at("once") is None
    store.mark_fired("once", "2026-05-01T09:00:00")
    assert store.fired_at("once") == "2026-05-01T09:00:00"
    store.mark_fired("once", "2026-06-01T09:00:00")
    assert store.fired_at("once") == "2026-06-01T09:00:00"


def test_fired_state_clear(store):
    store.mark_fired("a", "2026-05-01T09:00:00")
    store.mark_fired("b", "2026-05-02T09:00:00")
    store.clear_fired("a")
    assert store.fired_at("a") is None
    assert store.fired_at("b") == "2026-05-02T09:00:00"


def test_fired_state_resilient_to_corrupt_file(store):
    store.state_path.parent.mkdir(parents=True, exist_ok=True)
    store.state_path.write_text("{not json")
    assert store.fired_at("x") is None
    store.mark_fired("x", "2026-05-01T09:00:00")
    assert store.fired_at("x") == "2026-05-01T09:00:00"
