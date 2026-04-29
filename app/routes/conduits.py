"""``/conduits`` REST routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response

from app.core.atelier import Atelier
from app.schemas.api import (
    ConduitDTO,
    CreateConduitInput,
    OpenPathInput,
    UpdateConduitInput,
)
from app.services.api.base import get_atelier


router = APIRouter(prefix="/conduits", tags=["conduits"])


def _error(message: str, code: int) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": message})


@router.get("")
async def list_conduits(atelier: Atelier = Depends(get_atelier)) -> list[dict]:
    """List every conduit visible to the facade (project + global)."""
    out: list[dict] = []
    for name in atelier.list_conduits():
        try:
            conduit = atelier.store.read_conduit(name)
        except FileNotFoundError:
            continue
        out.append(ConduitDTO.model_validate(conduit.model_dump()).model_dump())
    return out


@router.get("/{name}")
async def get_conduit(name: str, atelier: Atelier = Depends(get_atelier)):
    try:
        conduit = atelier.store.read_conduit(name)
    except FileNotFoundError as e:
        return _error(str(e), 404)
    return ConduitDTO.model_validate(conduit.model_dump()).model_dump()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conduit(
    payload: CreateConduitInput, atelier: Atelier = Depends(get_atelier)
):
    try:
        conduit = atelier.create_conduit(payload)
    except FileExistsError as e:
        return _error(str(e), 409)
    except ValueError as e:
        return _error(str(e), 400)
    return ConduitDTO.model_validate(conduit.model_dump()).model_dump()


@router.patch("/{name}")
async def update_conduit(
    name: str,
    payload: UpdateConduitInput,
    atelier: Atelier = Depends(get_atelier),
):
    try:
        conduit = atelier.update_conduit(name, payload)
    except FileNotFoundError as e:
        return _error(str(e), 404)
    except ValueError as e:
        return _error(str(e), 400)
    return ConduitDTO.model_validate(conduit.model_dump()).model_dump()


@router.delete("/{name}")
async def delete_conduit(name: str, atelier: Atelier = Depends(get_atelier)):
    if not atelier.delete_conduit(name):
        return _error(f"conduit not found: {name}", 404)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/open-path")
async def open_path(
    payload: OpenPathInput, atelier: Atelier = Depends(get_atelier)
) -> dict[str, Any]:
    opened = atelier.open_conduit_path(payload.conduit_name, payload.run_path)
    return {"opened": opened}
