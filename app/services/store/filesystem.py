"""Filesystem-backed implementation of StoreBase.

Manages the on-disk layout:

    <base>/
    ├── conduits/<name>/conduit.yaml
    └── flows/<flow_id>/
        ├── input.yaml
        ├── logs.json
        ├── progress.json
        └── flows/<child_flow_id>/...

Nested (child) flows live under `<parent>/flows/<child_id>/`. The store tracks
parent->child relationships via an in-memory map keyed on `parent_flow_id`.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.schemas.conduit import Conduit
from app.schemas.flow import new_flow_id
from app.schemas.log import LogEntry
from app.schemas.progress import Progress
from app.services.store.base import ConduitSource, StoreBase


class FilesystemStore(StoreBase):
    def __init__(
        self,
        base_dir: Path | str,
        global_dir: Path | str | None = None,
    ):
        """Initialise the filesystem store with project and optional global dirs.

        :param base_dir: project-level ``.atelier/`` directory
        :param global_dir: optional user-level directory for shared conduits
        """
        self.base_dir = Path(base_dir)
        (self.base_dir / "conduits").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "flows").mkdir(parents=True, exist_ok=True)
        self.global_dir: Path | None = Path(global_dir) if global_dir else None
        if self.global_dir is not None:
            try:
                (self.global_dir / "conduits").mkdir(parents=True, exist_ok=True)
            except OSError:
                # Read-only HOME / sandbox — degrade to project-only mode.
                self.global_dir = None
        self._log_locks: dict[str, asyncio.Lock] = {}
        self._flow_paths: dict[str, Path] = {}

    # ------------------------------------------------------------------ paths

    def _conduit_dir(self, name: str) -> Path:
        """Return the project-level directory for conduit ``name``.

        :param name: conduit name
        """
        return self.base_dir / "conduits" / name

    def _conduit_yaml(self, name: str) -> Path:
        """Return the project-level ``conduit.yaml`` path for ``name``.

        :param name: conduit name
        """
        return self._conduit_dir(name) / "conduit.yaml"

    def _global_conduit_yaml(self, name: str) -> Path | None:
        """Return the global ``conduit.yaml`` path for ``name`` or ``None``.

        :param name: conduit name
        """
        if self.global_dir is None:
            return None
        return self.global_dir / "conduits" / name / "conduit.yaml"

    def _flow_dir(self, flow_id: str) -> Path:
        """Resolve and cache the directory for ``flow_id``.

        :param flow_id: flow identifier
        """
        if flow_id in self._flow_paths:
            return self._flow_paths[flow_id]
        # fall-back: search (for CLI `status`/`list` after restart)
        for candidate in self.base_dir.rglob(flow_id):
            if candidate.is_dir() and candidate.name == flow_id:
                self._flow_paths[flow_id] = candidate
                return candidate
        raise FileNotFoundError(f"flow not found: {flow_id}")

    # ------------------------------------------------------------------ conduits

    def read_conduit(self, name: str) -> Conduit:
        """Load conduit ``name`` from the project store, falling back to global.

        :param name: conduit name
        """
        project_path = self._conduit_yaml(name)
        global_path = self._global_conduit_yaml(name)
        if project_path.exists():
            path = project_path
        elif global_path is not None and global_path.exists():
            path = global_path
        else:
            raise FileNotFoundError(f"conduit not found: {name} ({project_path})")
        data = yaml.safe_load(path.read_text())
        conduit = Conduit.model_validate(data)
        if conduit.name != name:
            raise ValueError(
                f"conduit.yaml name {conduit.name!r} != folder name {name!r}"
            )
        return conduit

    def _scan_conduits_dir(self, root: Path) -> list[str]:
        """List conduit names under ``root`` that have a ``conduit.yaml``.

        :param root: directory expected to contain ``<name>/conduit.yaml``
        """
        if not root.exists():
            return []
        return sorted(
            p.name
            for p in root.iterdir()
            if p.is_dir() and (p / "conduit.yaml").exists()
        )

    def list_conduits(self) -> list[str]:
        """Return all visible conduit names from project and global stores."""
        return [name for name, _ in self.list_conduits_with_source()]

    def list_conduits_with_source(self) -> list[tuple[str, ConduitSource]]:
        """Return ``(name, source)`` pairs; project shadows global on collision."""
        project_names = set(self._scan_conduits_dir(self.base_dir / "conduits"))
        global_names: set[str] = set()
        if self.global_dir is not None:
            global_names = set(
                self._scan_conduits_dir(self.global_dir / "conduits")
            )
        entries: list[tuple[str, ConduitSource]] = []
        for name in sorted(project_names | global_names):
            source: ConduitSource = "project" if name in project_names else "global"
            entries.append((name, source))
        return entries

    def write_conduit(self, conduit: Conduit) -> None:
        """Persist ``conduit`` under ``conduits/<name>/conduit.yaml``.

        :param conduit: validated conduit to persist (overwrites if present)
        """
        conduit_dir = self._conduit_dir(conduit.name)
        conduit_dir.mkdir(parents=True, exist_ok=True)
        payload = conduit.model_dump(mode="json", by_alias=True, exclude_none=True)
        path = self._conduit_yaml(conduit.name)
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload, sort_keys=False))
        os.replace(tmp, path)

    def delete_conduit(self, name: str) -> bool:
        """Remove ``conduits/<name>/`` if present (project store only).

        :param name: conduit name
        :returns: True if deleted, False if it didn't exist
        """
        conduit_dir = self._conduit_dir(name)
        if not conduit_dir.exists():
            return False
        shutil.rmtree(conduit_dir)
        return True

    # ------------------------------------------------------------------ flows

    def create_flow(
        self,
        conduit_name: str,
        inputs: dict[str, Any],
        parent_flow_id: str | None = None,
    ) -> str:
        """Create a new flow directory and seed its tracking files.

        :param conduit_name: conduit being run
        :param inputs: initial input map persisted to ``input.yaml``
        :param parent_flow_id: optional parent flow for nested runs
        :returns: the freshly generated flow id
        """
        flow_id = new_flow_id(conduit_name)
        if parent_flow_id is None:
            flow_dir = self.base_dir / "flows" / flow_id
        else:
            flow_dir = self._flow_dir(parent_flow_id) / "flows" / flow_id
        flow_dir.mkdir(parents=True, exist_ok=True)
        (flow_dir / "flows").mkdir(exist_ok=True)
        self._flow_paths[flow_id] = flow_dir
        # input.yaml
        (flow_dir / "input.yaml").write_text(yaml.safe_dump(inputs, sort_keys=False))
        # logs.json
        (flow_dir / "logs.json").write_text("[]\n")
        # progress.json (empty shell; engine writes real content immediately)
        (flow_dir / "progress.json").write_text(
            json.dumps(
                {
                    "status": "running",
                    "current_tasks": [],
                    "tasks": {},
                    "started_at": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "finished_at": None,
                },
                indent=2,
            )
        )
        return flow_id

    def list_flows(self, conduit_name: str | None = None) -> list[str]:
        """List top-level flow ids, optionally filtered by conduit prefix.

        :param conduit_name: when set, only flows starting with ``<name>_`` are returned
        """
        root = self.base_dir / "flows"
        if not root.exists():
            return []
        ids: list[str] = []
        for p in root.iterdir():
            if p.is_dir():
                if conduit_name is None or p.name.startswith(conduit_name + "_"):
                    ids.append(p.name)
        return sorted(ids)

    # ------------------------------------------------------------------ logs

    def _lock_for(self, flow_id: str) -> asyncio.Lock:
        """Return (lazily creating) the asyncio lock guarding ``flow_id`` logs.

        :param flow_id: flow identifier
        """
        lock = self._log_locks.get(flow_id)
        if lock is None:
            lock = asyncio.Lock()
            self._log_locks[flow_id] = lock
        return lock

    async def append_log(self, flow_id: str, entry: LogEntry) -> None:
        """Append ``entry`` to the flow's ``logs.json`` under a per-flow lock.

        :param flow_id: flow identifier
        :param entry: log entry to append
        """
        path = self._flow_dir(flow_id) / "logs.json"
        async with self._lock_for(flow_id):
            try:
                existing = json.loads(path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                existing = []
            existing.append(entry.model_dump())
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(existing, indent=2))
            os.replace(tmp, path)

    def read_logs(self, flow_id: str) -> list[LogEntry]:
        """Return all log entries for ``flow_id`` in append order.

        :param flow_id: flow identifier
        :returns: parsed list of :class:`LogEntry` — empty if missing/unreadable
        """
        path = self._flow_dir(flow_id) / "logs.json"
        try:
            raw = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return [LogEntry.model_validate(item) for item in raw]

    # ------------------------------------------------------------------ progress

    def write_progress(self, flow_id: str, progress: Progress) -> None:
        """Atomically write ``progress.json`` for ``flow_id``.

        :param flow_id: flow identifier
        :param progress: progress snapshot to persist
        """
        path = self._flow_dir(flow_id) / "progress.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(progress.model_dump_json(indent=2))
        os.replace(tmp, path)

    def read_progress(self, flow_id: str) -> Progress:
        """Load and return the ``Progress`` snapshot for ``flow_id``.

        :param flow_id: flow identifier
        """
        path = self._flow_dir(flow_id) / "progress.json"
        return Progress.model_validate_json(path.read_text())

    # ------------------------------------------------------------------ outputs.yaml

    def write_outputs(self, flow_id: str, outputs: dict[str, Any]) -> None:
        """Atomically write ``outputs.yaml`` for ``flow_id``.

        :param flow_id: flow identifier
        :param outputs: mapping of task name to final output (``None`` for tasks
            that did not complete)
        """
        path = self._flow_dir(flow_id) / "outputs.yaml"
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(outputs, sort_keys=False))
        os.replace(tmp, path)

    # ------------------------------------------------------------------ input.yaml

    def read_input(self, flow_id: str) -> dict[str, Any]:
        """Return the parsed ``input.yaml`` map for ``flow_id`` (empty if missing).

        :param flow_id: flow identifier
        """
        path = self._flow_dir(flow_id) / "input.yaml"
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    def append_input(self, flow_id: str, key: str, value: Any) -> None:
        """Set ``key=value`` in the flow's ``input.yaml``.

        :param flow_id: flow identifier
        :param key: input key to add or overwrite
        :param value: value to store under ``key``
        """
        path = self._flow_dir(flow_id) / "input.yaml"
        existing: dict[str, Any] = {}
        if path.exists():
            loaded = yaml.safe_load(path.read_text())
            if isinstance(loaded, dict):
                existing = loaded
        existing[key] = value
        path.write_text(yaml.safe_dump(existing, sort_keys=False))
