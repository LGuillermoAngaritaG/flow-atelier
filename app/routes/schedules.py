"""``/schedules`` REST routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.atelier import Atelier
from app.schemas.api import CreateScheduleInput
from app.services.api.base import get_atelier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["schedules"])


def _error(message: str, code: int) -> JSONResponse:
    """Build a uniform ``{"error": message}`` JSON response.

    :param message: human-readable error message.
    :param code: HTTP status code to return.
    :returns: a :class:`JSONResponse` with the given status and body.
    """
    return JSONResponse(status_code=code, content={"error": message})


@router.get("")
async def list_schedules(atelier: Atelier = Depends(get_atelier)) -> list[dict]:
    """Return every persisted :class:`ScheduledJob`.

    :param atelier: injected :class:`Atelier` facade.
    :returns: JSON-serializable dicts for each scheduled job.
    """
    return [job.model_dump(mode="json") for job in atelier.list_schedules()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: CreateScheduleInput, atelier: Atelier = Depends(get_atelier)
):
    """Create a scheduled job and hot-sync the embedded daemon if attached.

    :param payload: parsed :class:`CreateScheduleInput` body.
    :param atelier: injected :class:`Atelier` facade.
    :returns: JSON-serializable dict of the created job.
    """
    job = atelier.create_schedule(payload)
    # Hot-register with the embedded daemon if one is attached.
    daemon = getattr(atelier, "scheduler_daemon", None)
    if daemon is not None:
        try:
            await daemon.sync()
        except Exception:  # noqa: BLE001 — daemon must survive sync errors
            logger.warning(
                "scheduler sync after create failed (schedule %s)",
                job.id,
                exc_info=True,
            )
    return job.model_dump(mode="json")


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str, atelier: Atelier = Depends(get_atelier)
):
    """Delete a scheduled job and hot-sync the embedded daemon if attached.

    :param schedule_id: identifier of the scheduled job from the URL path.
    :param atelier: injected :class:`Atelier` facade.
    :returns: JSON-serializable dict of the deleted job or an error response.
    """
    try:
        job = atelier.delete_schedule(schedule_id)
    except KeyError as e:
        return _error(str(e), 404)
    daemon = getattr(atelier, "scheduler_daemon", None)
    if daemon is not None:
        try:
            await daemon.sync()
        except Exception:  # noqa: BLE001
            logger.warning(
                "scheduler sync after delete failed (schedule %s)",
                schedule_id,
                exc_info=True,
            )
    return job.model_dump(mode="json")
