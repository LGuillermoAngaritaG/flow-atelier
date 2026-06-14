"""Atelier facade: schedule CRUD."""
from __future__ import annotations

import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.api import CreateScheduleInput, ScheduledJob


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    """Construct an Atelier instance rooted under tmp_path.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    # create_schedule validates conduit_name against the store, so the
    # conduit the fixtures schedule must exist on disk.
    conduit_dir = tmp_path / ".atelier" / "conduits" / "report"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: report\n"
        "description: test conduit\n"
        "tasks:\n"
        "  - greet:\n"
        "      description: say hi\n"
        '      task: "echo hi"\n'
        "      tool: tool:bash\n"
        "      depends_on: []\n"
    )
    return atelier


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


def test_create_schedule_rejects_unknown_conduit(atelier):
    """Verify create_schedule rejects a conduit_name with no conduit on disk.

    :param atelier: Atelier facade fixture.
    """
    with pytest.raises(ValueError, match="unknown conduit"):
        atelier.create_schedule(_payload(conduit_name="does-not-exist"))
    assert atelier.list_schedules() == []


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
