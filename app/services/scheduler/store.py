"""JSON-backed schedule store (per SPEC §7).

Two files in ``<atelier>/``:

- ``schedules.json``: array of :class:`ScheduledJob` records. Soft-delete
  via ``status="deleted"``; the file never shrinks, but :meth:`list` only
  surfaces active rows.
- ``scheduler_state.json``: fired-once markers keyed by schedule ``id``.

Atomic writes via ``os.replace``. The store does not migrate legacy
``.atelier/schedules/*.yaml`` files — those are silently ignored.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.schemas.api import CreateScheduleInput, ScheduledJob


class ScheduleStore:
    """JSON-backed CRUD for :class:`ScheduledJob` records.

    :param atelier_dir: project ``.atelier/`` directory; created if missing
    """

    def __init__(self, atelier_dir: Path | str) -> None:
        self.atelier_dir = Path(atelier_dir)
        self.atelier_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_path = self.atelier_dir / "schedules.json"
        self.state_path = self.atelier_dir / "scheduler_state.json"

    # --------------------------------------------------------------- internals

    def _read_all(self) -> list[ScheduledJob]:
        if not self.schedules_path.exists():
            return []
        try:
            raw = json.loads(self.schedules_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, dict):
            return []
        items = raw.get("schedules", [])
        if not isinstance(items, list):
            return []
        out: list[ScheduledJob] = []
        for entry in items:
            try:
                out.append(ScheduledJob.model_validate(entry))
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
        return out

    def _write_all(self, jobs: list[ScheduledJob]) -> None:
        payload = {"schedules": [j.model_dump(mode="json") for j in jobs]}
        tmp = self.schedules_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.schedules_path)

    # --------------------------------------------------------------- list / get

    def list(self) -> list[ScheduledJob]:
        """Return all schedules with ``status == 'active'``."""
        return [j for j in self._read_all() if j.status == "active"]

    def list_all(self) -> list[ScheduledJob]:
        """Return every persisted schedule (including soft-deleted)."""
        return self._read_all()

    def get(self, schedule_id: str) -> ScheduledJob | None:
        """Return the active schedule matching ``schedule_id`` or ``None``."""
        for job in self._read_all():
            if job.id == schedule_id and job.status == "active":
                return job
        return None

    def get_by_name(self, name: str) -> ScheduledJob | None:
        """Find the first active schedule whose ``schedule.name`` matches."""
        for job in self._read_all():
            if job.status == "active" and job.schedule.name == name:
                return job
        return None

    # --------------------------------------------------------------- create / delete

    def create(self, payload: CreateScheduleInput) -> ScheduledJob:
        """Persist a new :class:`ScheduledJob` derived from ``payload``."""
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
        all_jobs = self._read_all()
        all_jobs.append(job)
        self._write_all(all_jobs)
        return job

    def delete(self, schedule_id: str) -> ScheduledJob:
        """Soft-delete the schedule (sets ``status='deleted'``).

        :raises KeyError: if no schedule exists for ``schedule_id``
        """
        all_jobs = self._read_all()
        for i, job in enumerate(all_jobs):
            if job.id == schedule_id:
                updated = job.model_copy(update={"status": "deleted"})
                all_jobs[i] = updated
                self._write_all(all_jobs)
                self.clear_fired(schedule_id)
                return updated
        raise KeyError(f"schedule not found: {schedule_id}")

    def increment_runs(self, schedule_id: str) -> None:
        """Bump ``runs_completed`` for ``schedule_id`` if it still exists."""
        all_jobs = self._read_all()
        for i, job in enumerate(all_jobs):
            if job.id == schedule_id:
                all_jobs[i] = job.model_copy(
                    update={"runs_completed": job.runs_completed + 1}
                )
                self._write_all(all_jobs)
                return

    # --------------------------------------------------------------- fired state

    def _read_state(self) -> dict[str, Any]:
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
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.state_path)

    def fired_at(self, schedule_id: str) -> str | None:
        """Return the ISO timestamp recorded for the last fire, or ``None``."""
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
            from datetime import datetime, timezone

            scheduled_at_iso = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        data = self._read_state()
        data["schedules"][schedule_id] = {"fired_at_iso": scheduled_at_iso}
        self._write_state(data)

    def clear_fired(self, schedule_id: str) -> None:
        data = self._read_state()
        if schedule_id in data["schedules"]:
            del data["schedules"][schedule_id]
            self._write_state(data)
