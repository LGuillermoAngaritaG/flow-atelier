"""``/tasks/run`` REST route."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.atelier import Atelier
from app.schemas.api import RunTaskInput, RunTaskOutput
from app.services.api.base import get_atelier


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/run")
async def run_task(
    payload: RunTaskInput, atelier: Atelier = Depends(get_atelier)
) -> dict:
    """Run an ad-hoc one-task conduit and return its flow_id + logs.

    :param payload: parsed :class:`RunTaskInput` body describing the task.
    :param atelier: injected :class:`Atelier` facade.
    :returns: JSON-serializable dict of the :class:`RunTaskOutput` result.
    """
    out: RunTaskOutput = await atelier.run_single_task(payload)
    return out.model_dump(mode="json")
