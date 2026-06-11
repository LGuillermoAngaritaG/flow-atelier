"""``/conduits`` REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.atelier import Atelier
from app.schemas.api import (
    ConduitDTO,
    CreateConduitInput,
    OpenPathInput,
    OpenPathOutput,
    UpdateConduitInput,
)
from app.services.api.base import get_atelier

router = APIRouter(prefix="/conduits", tags=["conduits"])


@router.get("", response_model=list[ConduitDTO])
async def list_conduits(atelier: Atelier = Depends(get_atelier)) -> list[ConduitDTO]:
    """List every conduit visible to the facade (project + global).

    :param atelier: injected :class:`Atelier` facade.
    :returns: :class:`ConduitDTO` for each readable conduit.
    """
    out: list[ConduitDTO] = []
    for name in atelier.list_conduits():
        try:
            conduit = atelier.store.read_conduit(name)
        except FileNotFoundError:
            continue
        out.append(ConduitDTO.model_validate(conduit.model_dump()))
    return out


@router.get("/{name}", response_model=ConduitDTO)
async def get_conduit(name: str, atelier: Atelier = Depends(get_atelier)) -> ConduitDTO:
    """Return one conduit by name or 404 if missing.

    :param name: conduit identifier from the URL path.
    :param atelier: injected :class:`Atelier` facade.
    :returns: the matching :class:`ConduitDTO`.
    """
    try:
        conduit = atelier.store.read_conduit(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ConduitDTO.model_validate(conduit.model_dump())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConduitDTO)
async def create_conduit(
    payload: CreateConduitInput, atelier: Atelier = Depends(get_atelier)
) -> ConduitDTO:
    """Create a new conduit, mapping known errors to HTTP status codes.

    :param payload: parsed :class:`CreateConduitInput` body.
    :param atelier: injected :class:`Atelier` facade.
    :returns: the created :class:`ConduitDTO`.
    """
    try:
        conduit = atelier.create_conduit(payload)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ConduitDTO.model_validate(conduit.model_dump())


@router.patch("/{name}", response_model=ConduitDTO)
async def update_conduit(
    name: str,
    payload: UpdateConduitInput,
    atelier: Atelier = Depends(get_atelier),
) -> ConduitDTO:
    """Patch an existing conduit, mapping known errors to HTTP status codes.

    :param name: conduit identifier from the URL path.
    :param payload: parsed :class:`UpdateConduitInput` body.
    :param atelier: injected :class:`Atelier` facade.
    :returns: the updated :class:`ConduitDTO`.
    """
    try:
        conduit = atelier.update_conduit(name, payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ConduitDTO.model_validate(conduit.model_dump())


@router.delete("/{name}")
async def delete_conduit(name: str, atelier: Atelier = Depends(get_atelier)) -> Response:
    """Delete a conduit by name, returning 204 on success or 404 if missing.

    :param name: conduit identifier from the URL path.
    :param atelier: injected :class:`Atelier` facade.
    :returns: empty 204 response.
    """
    if not atelier.delete_conduit(name):
        raise HTTPException(status_code=404, detail=f"conduit not found: {name}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/open-path", response_model=OpenPathOutput)
async def open_path(
    payload: OpenPathInput, atelier: Atelier = Depends(get_atelier)
) -> OpenPathOutput:
    """Open a path in the host OS file explorer.

    :param payload: parsed :class:`OpenPathInput` body.
    :param atelier: injected :class:`Atelier` facade.
    :returns: whether the path was opened.
    """
    return OpenPathOutput(opened=atelier.open_conduit_path(payload.run_path))
