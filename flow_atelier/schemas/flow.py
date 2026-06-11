"""Flow schema and flow-id helpers."""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

FLOW_ID_RE = re.compile(r"^(?P<date>\d{8})_(?P<uuid>[0-9a-f]{8})_(?P<conduit>.+)$")


def new_flow_id(conduit_name: str) -> str:
    """Build a filesystem-safe flow id: <YYYYMMDD>_<uuid8>_<conduit>.

    :param conduit_name: name of the conduit this flow belongs to.
    :returns: a new flow id string composed of UTC date, short uuid, and conduit name.
    """
    date = datetime.now(UTC).strftime("%Y%m%d")
    return f"{date}_{uuid.uuid4().hex[:8]}_{conduit_name}"


def parse_flow_id(flow_id: str) -> tuple[str, str, str]:
    """Return (conduit_name, uuid8, date) — raises ValueError if invalid.

    :param flow_id: a flow id previously built by :func:`new_flow_id`.
    :returns: a tuple of ``(conduit_name, uuid8, date)`` parsed from the id.
    """
    m = FLOW_ID_RE.match(flow_id)
    if not m:
        raise ValueError(f"Invalid flow id: {flow_id!r}")
    return m.group("conduit"), m.group("uuid"), m.group("date")


class Flow(BaseModel):
    """An in-memory representation of a single flow run."""

    flow_id: str
    conduit_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    parent_flow_id: str | None = None
