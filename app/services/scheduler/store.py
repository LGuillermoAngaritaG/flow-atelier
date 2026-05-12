"""YAML-backed schedule store.

Layout under ``<atelier>/``:

- ``schedules/<slug(name)>.yaml``: one file per :class:`ScheduledJob`.
  Deletes remove the file. The original ``schedule.name`` is preserved
  inside the YAML; the filename is a filesystem-safe slug of that name.
- ``scheduler_state.json``: fired-once markers keyed by schedule ``id``.

Atomic writes via ``os.replace``.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml

from app.schemas.api import CreateScheduleInput, ScheduledJob

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(name: str) -> str:
    """Reduce ``name`` to a filesystem-safe lowercase slug.

    :param name: human-readable schedule name
    :raises ValueError: when the slug would be empty
    """
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"schedule name has no filesystem-safe characters: {name!r}")
    return slug


class ScheduleStore:
    """YAML-backed CRUD for :class:`ScheduledJob` records.

    :param atelier_dir: project ``.atelier/`` directory; created if missing
    """

    def __init__(self, atelier_dir: Path | str) -> None:
        """Initialise the store rooted at ``atelier_dir``.

        :param atelier_dir: project ``.atelier/`` directory; created if missing
        """
        self.atelier_dir = Path(atelier_dir)
        self.atelier_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_dir = self.atelier_dir / "schedules"
        self.schedules_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.atelier_dir / "scheduler_state.json"

    # --------------------------------------------------------------- internals

    def _path_for_name(self, name: str) -> Path:
        """Return the YAML path for ``name``.

        :param name: schedule name
        """
        return self.schedules_dir / f"{_slug(name)}.yaml"

    def _load_file(self, path: Path) -> ScheduledJob | None:
        """Load and validate one schedule YAML; return None on failure.

        :param path: path to a ``*.yaml`` schedule file
        """
        try:
            raw = yaml.safe_load(path.read_text())
        except (yaml.YAMLError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return ScheduledJob.model_validate(raw)
        except Exception:  # noqa: BLE001 — skip malformed rows
            return None

    def _save_job(self, job: ScheduledJob) -> None:
        """Atomically write ``job`` to its YAML file.

        :param job: schedule to persist
        """
        path = self._path_for_name(job.schedule.name)
        payload = job.model_dump(mode="json", exclude_none=True)
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload, sort_keys=False))
        os.replace(tmp, path)

    def _iter_jobs(self) -> list[ScheduledJob]:
        """Return every persisted schedule, sorted by ``created_at`` ascending."""
        if not self.schedules_dir.exists():
            return []
        jobs: list[ScheduledJob] = []
        for path in self.schedules_dir.glob("*.yaml"):
            job = self._load_file(path)
            if job is not None:
                jobs.append(job)
        jobs.sort(key=lambda j: j.created_at)
        return jobs

    # --------------------------------------------------------------- list / get

    def list(self) -> list[ScheduledJob]:
        """Return all schedules with ``status == 'active'``."""
        return [j for j in self._iter_jobs() if j.status == "active"]

    def list_all(self) -> list[ScheduledJob]:
        """Return every persisted schedule."""
        return self._iter_jobs()

    def get(self, schedule_id: str) -> ScheduledJob | None:
        """Return the active schedule matching ``schedule_id`` or ``None``.

        :param schedule_id: schedule identifier
        """
        for job in self._iter_jobs():
            if job.id == schedule_id and job.status == "active":
                return job
        return None

    def get_by_name(self, name: str) -> ScheduledJob | None:
        """Find the first active schedule whose ``schedule.name`` matches.

        :param name: schedule name to look up
        """
        for job in self._iter_jobs():
            if job.status == "active" and job.schedule.name == name:
                return job
        return None

    # --------------------------------------------------------------- create / delete

    def create(self, payload: CreateScheduleInput) -> ScheduledJob:
        """Persist a new :class:`ScheduledJob` derived from ``payload``.

        :param payload: validated input describing the new schedule
        :raises ValueError: if ``payload.schedule.name`` is empty
        :raises FileExistsError: if a schedule with the same slug already exists
        """
        name = payload.schedule.name
        if not name.strip():
            raise ValueError("schedule.name must be non-empty")
        path = self._path_for_name(name)
        if path.exists():
            raise FileExistsError(
                f"schedule already exists for name {name!r} ({path.name})"
            )
        job = ScheduledJob(
            id=f"SCH-{uuid.uuid4().hex[:12]}",
            conduit_name=payload.conduit_name,
            inputs=dict(payload.inputs),
            run_path=payload.run_path,
            schedule=payload.schedule,
            created_at=int(time.time() * 1000),
            status="active",
            runs_completed=0,
        )
        self._save_job(job)
        return job

    def delete(self, schedule_id: str) -> ScheduledJob:
        """Remove the schedule's YAML file and clear its fired marker.

        :param schedule_id: schedule identifier
        :raises KeyError: if no schedule exists for ``schedule_id``
        :returns: the deleted job with ``status='deleted'`` set in-memory
        """
        for job in self._iter_jobs():
            if job.id == schedule_id:
                path = self._path_for_name(job.schedule.name)
                if path.exists():
                    path.unlink()
                self.clear_fired(schedule_id)
                return job.model_copy(update={"status": "deleted"})
        raise KeyError(f"schedule not found: {schedule_id}")

    def increment_runs(self, schedule_id: str) -> None:
        """Bump ``runs_completed`` for ``schedule_id`` if it still exists.

        :param schedule_id: schedule identifier
        """
        for job in self._iter_jobs():
            if job.id == schedule_id:
                self._save_job(
                    job.model_copy(update={"runs_completed": job.runs_completed + 1})
                )
                return

    # --------------------------------------------------------------- fired state

    def _read_state(self) -> dict[str, Any]:
        """Load the ``scheduler_state.json`` payload, returning a safe default."""
        if not self.state_path.exists():
            return {"schedules": {}}
        try:
            data = json.loads(self.state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"schedules": {}}
        if not isinstance(data, dict) or "schedules" not in data:
            return {"schedules": {}}
        return data

    def _write_state(self, data: dict[str, Any]) -> None:
        """Atomically replace ``scheduler_state.json`` with ``data``.

        :param data: full state payload to persist
        """
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.state_path)

    def fired_at(self, schedule_id: str) -> str | None:
        """Return the ISO timestamp recorded for the last fire, or ``None``.

        :param schedule_id: schedule identifier
        """
        data = self._read_state()
        entry = data["schedules"].get(schedule_id)
        if not isinstance(entry, dict):
            return None
        value = entry.get("fired_at_iso")
        return value if isinstance(value, str) else None

    def mark_fired(self, schedule_id: str, scheduled_at_iso: str | None = None) -> None:
        """Record that ``schedule_id`` has fired.

        :param schedule_id: schedule identifier
        :param scheduled_at_iso: optional ISO timestamp; defaults to now
        """
        if scheduled_at_iso is None:
            from datetime import datetime

            scheduled_at_iso = (
                datetime.now(UTC).isoformat().replace("+00:00", "Z")
            )
        data = self._read_state()
        data["schedules"][schedule_id] = {"fired_at_iso": scheduled_at_iso}
        self._write_state(data)

    def clear_fired(self, schedule_id: str) -> None:
        """Drop the fired-once marker for ``schedule_id`` if present.

        :param schedule_id: schedule identifier
        """
        data = self._read_state()
        if schedule_id in data["schedules"]:
            del data["schedules"][schedule_id]
            self._write_state(data)
