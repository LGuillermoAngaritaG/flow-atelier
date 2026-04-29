"""``/schedules`` REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput
from app.services.api.base import get_atelier


router = APIRouter(prefix="/schedules", tags=["schedules"])


def _error(message: str, code: int) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": message})


@router.get("")
async def list_schedules(atelier: Atelier = Depends(get_atelier)) -> list[dict]:
    """Return active :class:`ScheduledJob` records."""
    return [job.model_dump(mode="json") for job in atelier.list_schedules()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: CreateScheduleInput, atelier: Atelier = Depends(get_atelier)
):
    job = atelier.create_schedule(payload)
    # Hot-register with the embedded daemon if one is attached.
    daemon = getattr(atelier, "scheduler_daemon", None)
    if daemon is not None:
        try:
            await daemon._sync_from_disk()  # noqa: SLF001
        except Exception:  # noqa: BLE001 — daemon must survive sync errors
            pass
    return job.model_dump(mode="json")


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str, atelier: Atelier = Depends(get_atelier)
):
    try:
        job = atelier.delete_schedule(schedule_id)
    except KeyError as e:
        return _error(str(e), 404)
    daemon = getattr(atelier, "scheduler_daemon", None)
    if daemon is not None:
        try:
            await daemon._sync_from_disk()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    return job.model_dump(mode="json")
