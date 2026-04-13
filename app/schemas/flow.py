"""Flow schema and flow-id helpers."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

FLOW_ID_RE = re.compile(r"^(?P<conduit>.+)_(?P<uuid>[0-9a-f]{8})_(?P<ts>\d{8}T\d{6}Z)$")


def new_flow_id(conduit_name: str) -> str:
    """Build a filesystem-safe flow id: <conduit>_<uuid8>_<YYYYMMDDTHHMMSSZ>."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{conduit_name}_{uuid.uuid4().hex[:8]}_{ts}"


def parse_flow_id(flow_id: str) -> tuple[str, str, str]:
    """Return (conduit_name, uuid8, timestamp) — raises ValueError if invalid."""
    m = FLOW_ID_RE.match(flow_id)
    if not m:
        raise ValueError(f"Invalid flow id: {flow_id!r}")
    return m.group("conduit"), m.group("uuid"), m.group("ts")


class Flow(BaseModel):
    """An in-memory representation of a single flow run."""

    flow_id: str
    conduit_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    parent_flow_id: str | None = None
