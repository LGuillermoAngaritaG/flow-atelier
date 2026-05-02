"""Per-sender ACP session id store backed by a single JSON file.

Persists ``{ "<channel>:<session_key>:<task>": {session_id, last_active_at} }``
to ``<atelier_dir>/channel_sessions.json``. Single-process serve, so no locking
is needed beyond atomic writes (temp-file + ``os.replace``). Reads are
TTL-aware: an entry older than ``ttl_seconds`` is treated as missing.

This is the "session resume key" half of the spec's per-sender ACP rule —
the registry pairs it with FIFO per-(channel, session_key) dispatch so two
quick messages from the same user run back-to-back on the same harness session.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 48 * 3600


class ChannelSessionStore:
    """JSON-backed CRUD for resumable channel session ids.

    :param atelier_dir: project ``.atelier/`` dir; created if missing
    :param ttl_seconds: entries older than this are reported as missing
    """

    def __init__(
        self,
        atelier_dir: Path | str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.atelier_dir = Path(atelier_dir)
        self.atelier_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.atelier_dir / "channel_sessions.json"
        self.ttl_seconds = ttl_seconds

    def _read_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("channel_sessions.json unreadable, ignoring: %s", e)
            return {}
        if not isinstance(raw, dict):
            return {}
        sessions = raw.get("sessions")
        if not isinstance(sessions, dict):
            return {}
        return sessions

    def _write_all(self, sessions: dict[str, dict[str, Any]]) -> None:
        payload = {"sessions": sessions}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, self.path)

    def get(self, key: str) -> str | None:
        """Return the live session id for ``key``, or ``None`` if missing/expired."""
        entry = self._read_all().get(key)
        if not isinstance(entry, dict):
            return None
        last = entry.get("last_active_at")
        if not isinstance(last, (int, float)):
            return None
        if time.time() - last > self.ttl_seconds:
            return None
        sid = entry.get("session_id")
        return sid if isinstance(sid, str) else None

    def set(self, key: str, session_id: str) -> None:
        """Persist ``session_id`` under ``key`` and bump ``last_active_at`` to now."""
        sessions = self._read_all()
        sessions[key] = {"session_id": session_id, "last_active_at": time.time()}
        self._write_all(sessions)

    def clear_prefix(self, prefix: str) -> int:
        """Remove every entry whose key starts with ``prefix``. Returns count removed."""
        sessions = self._read_all()
        to_remove = [k for k in sessions if k.startswith(prefix)]
        if not to_remove:
            return 0
        for k in to_remove:
            del sessions[k]
        self._write_all(sessions)
        return len(to_remove)
