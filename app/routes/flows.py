"""``/flows`` REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.atelier import Atelier
from app.services.api.base import get_atelier


router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("")
async def list_flows(atelier: Atelier = Depends(get_atelier)) -> list[dict]:
    return [pf.model_dump(mode="json") for pf in atelier.list_prior_flows()]


@router.get("/{flow_id}/logs")
async def get_flow_logs(
    flow_id: str, atelier: Atelier = Depends(get_atelier)
):
    try:
        logs = atelier.get_flow_logs(flow_id)
    except FileNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    return [entry.model_dump(mode="json") for entry in logs]
