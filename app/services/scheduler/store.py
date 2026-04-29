"""On-disk CRUD for schedules and fired-state tracking.

Layout::

    <schedules_dir>/
    ├── <name>.yaml          # one ScheduleDefinition per file
    └── .state.json          # one-shot fired markers, not user-editable

The store treats YAML as the source of truth — there is no DB. Fired-state
is a small JSON map so a daemon restart does not re-run a one-shot whose
``at`` has already passed.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas.schedule import ScheduleDefinition


@dataclass(frozen=True)
class LoadedSchedule:
    """A successfully parsed schedule with disk metadata."""

    definition: ScheduleDefinition
    source_path: Path
    mtime: float


@dataclass(frozen=True)
class ScheduleLoadError:
    """A YAML file that failed to parse, kept so the CLI/daemon can surface it."""

    source_path: Path
    error: str


class ScheduleStore:
    """Project-local schedule directory + fired-state JSON."""

    def __init__(
        self,
        schedules_dir: Path | str,
        state_path: Path | str | None = None,
    ) -> None:
        self.schedules_dir = Path(schedules_dir)
        self.schedules_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else self.schedules_dir / ".state.json"
        )

    # ------------------------------------------------------------------ paths

    def path_for(self, name: str) -> Path:
        return self.schedules_dir / f"{name}.yaml"

    # ------------------------------------------------------------------ load

    def _yaml_files(self) -> list[Path]:
        if not self.schedules_dir.exists():
            return []
        return sorted(
            p for p in self.schedules_dir.iterdir()
            if p.is_file() and p.suffix in (".yaml", ".yml") and not p.name.startswith(".")
        )

    def list_definitions(self) -> list[LoadedSchedule]:
        loaded, _errors = self.list_definitions_with_errors()
        return loaded

    def list_definitions_with_errors(
        self,
    ) -> tuple[list[LoadedSchedule], list[ScheduleLoadError]]:
        loaded: list[LoadedSchedule] = []
        errors: list[ScheduleLoadError] = []
        for path in self._yaml_files():
            try:
                definition = self._parse(path)
            except (ValidationError, ValueError, yaml.YAMLError, OSError) as e:
                errors.append(ScheduleLoadError(source_path=path, error=str(e)))
                continue
            loaded.append(
                LoadedSchedule(
                    definition=definition,
                    source_path=path,
                    mtime=path.stat().st_mtime,
                )
            )
        return loaded, errors

    def read(self, name: str) -> ScheduleDefinition:
        path = self.path_for(name)
        if not path.exists():
            raise FileNotFoundError(f"schedule not found: {name} ({path})")
        return self._parse(path)

    def _parse(self, path: Path) -> ScheduleDefinition:
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: top-level YAML must be a mapping")
        # Filename stem is the canonical schedule name; allow YAML to omit
        # `name:` and patch it in. If both are present they must match.
        stem = path.stem
        if "name" not in raw:
            raw["name"] = stem
        elif raw["name"] != stem:
            raise ValueError(
                f"{path}: schedule name {raw['name']!r} != filename stem {stem!r}"
            )
        return ScheduleDefinition.model_validate(raw)

    # ------------------------------------------------------------------ write

    def write(
        self,
        definition: ScheduleDefinition,
        *,
        force: bool = False,
    ) -> Path:
        path = self.path_for(definition.name)
        if path.exists() and not force:
            raise FileExistsError(f"schedule already exists: {definition.name} ({path})")
        payload = definition.model_dump(mode="json", exclude_none=True)
        # Drop the name field when writing — it's implied by the filename
        # and the loader will patch it back in. Avoids the accidental
        # mismatch class of bugs.
        payload.pop("name", None)
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        return path

    def install(self, source_path: Path | str, *, force: bool = False) -> Path:
        """Copy a user-supplied YAML file into ``schedules_dir``.

        Validates the YAML before installing so we never persist a broken
        schedule. The destination filename is ``<definition.name>.yaml``,
        which may differ from the source filename.
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"file not found: {source}")
        raw = yaml.safe_load(source.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{source}: top-level YAML must be a mapping")
        if "name" not in raw:
            raw["name"] = source.stem
        definition = ScheduleDefinition.model_validate(raw)
        dest = self.path_for(definition.name)
        if dest.exists() and not force:
            raise FileExistsError(
                f"schedule already exists: {definition.name} ({dest})"
            )
        if source.resolve() == dest.resolve():
            return dest
        shutil.copyfile(source, dest)
        # Re-parse to confirm the copy round-trips.
        self._parse(dest)
        return dest

    def remove(self, name: str) -> bool:
        path = self.path_for(name)
        existed = path.exists()
        if existed:
            path.unlink()
        self.clear_fired(name)
        return existed

    # ------------------------------------------------------------------ fired-state

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"schedules": {}}
        try:
            data = json.loads(self.state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"schedules": {}}
        if not isinstance(data, dict) or "schedules" not in data:
            return {"schedules": {}}
        return data

    def _save_state(self, data: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.state_path)

    def fired_at(self, name: str) -> str | None:
        """Return ISO timestamp of the scheduled-at of the last fire, or None."""
        data = self._load_state()
        entry = data["schedules"].get(name)
        if not isinstance(entry, dict):
            return None
        value = entry.get("fired_at_scheduled_iso")
        return value if isinstance(value, str) else None

    def mark_fired(self, name: str, scheduled_at_iso: str) -> None:
        data = self._load_state()
        data["schedules"][name] = {"fired_at_scheduled_iso": scheduled_at_iso}
        self._save_state(data)

    def clear_fired(self, name: str) -> None:
        data = self._load_state()
        if name in data["schedules"]:
            del data["schedules"][name]
            self._save_state(data)
