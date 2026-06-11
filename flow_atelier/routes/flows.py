"""``/flows`` REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.api import FlowLogsOutput, PriorFlow
from flow_atelier.services.api.base import get_atelier

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("", response_model=list[PriorFlow])
async def list_flows(atelier: Atelier = Depends(get_atelier)) -> list[PriorFlow]:
    """List prior flow runs known to the facade.

    :param atelier: injected :class:`Atelier` facade.
    :returns: :class:`PriorFlow` entries for each prior flow.
    """
    return atelier.list_prior_flows()


@router.get("/{flow_id}/logs", response_model=FlowLogsOutput)
async def get_flow_logs(
    flow_id: str, atelier: Atelier = Depends(get_atelier)
) -> FlowLogsOutput:
    """Return persisted log entries for ``flow_id`` or 404 if missing.

    :param flow_id: flow identifier from the URL path.
    :param atelier: injected :class:`Atelier` facade.
    :returns: the flow's run path, log entries, and child flow ids.
    """
    try:
        logs = atelier.get_flow_logs(flow_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    children = atelier.store.list_child_flows(flow_id)
    return FlowLogsOutput(
        run_path=atelier.store.read_input(flow_id).get("run_path"),
        logs=logs,
        children=children,
    )
