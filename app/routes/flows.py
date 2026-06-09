"""``/flows`` REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.atelier import Atelier
from app.services.api.base import get_atelier

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("")
async def list_flows(atelier: Atelier = Depends(get_atelier)) -> list[dict]:
    """List prior flow runs known to the facade.

    :param atelier: injected :class:`Atelier` facade.
    :returns: JSON-serializable dicts for each prior flow.
    """
    return [pf.model_dump(mode="json") for pf in atelier.list_prior_flows()]


@router.get("/{flow_id}/logs")
async def get_flow_logs(
    flow_id: str, atelier: Atelier = Depends(get_atelier)
):
    """Return persisted log entries for ``flow_id`` or 404 if missing.

    :param flow_id: flow identifier from the URL path.
    :param atelier: injected :class:`Atelier` facade.
    :returns: list of serialized log entries or an error response.
    """
    try:
        logs = atelier.get_flow_logs(flow_id)
    except FileNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    children = atelier.store.list_child_flows(flow_id)
    return {
        "run_path": atelier.store.read_input(flow_id).get("run_path"),
        "logs": [entry.model_dump(mode="json") for entry in logs],
        "children": children,
    }
