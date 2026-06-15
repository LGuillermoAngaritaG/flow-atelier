"""``/tasks/run`` REST route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.api import RunTaskInput, RunTaskOutput
from flow_atelier.services.api.base import get_atelier

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/run", response_model=RunTaskOutput)
async def run_task(
    payload: RunTaskInput, atelier: Atelier = Depends(get_atelier)
) -> RunTaskOutput:
    """Run an ad-hoc one-task conduit and return its flow_id + logs.

    :param payload: parsed :class:`RunTaskInput` body describing the task.
    :param atelier: injected :class:`Atelier` facade.
    :returns: the :class:`RunTaskOutput` result.
    """
    try:
        return await atelier.run_single_task(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
