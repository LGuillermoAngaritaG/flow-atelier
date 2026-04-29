"""``/ws/run-conduit`` WebSocket route."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from pydantic import TypeAdapter, ValidationError
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.atelier import Atelier
from app.schemas.log import TaskEvent
from app.schemas.progress import TaskStatus
from app.schemas.ws import (
    CancelMessage,
    ClientMessage,
    HitlAnswerMessage,
    RunMessage,
)
from app.services.api.base import get_atelier
from app.services.api.ws_hitl import WsHitlExecutor
from app.services.api.ws_manager import WebSocketBroker


logger = logging.getLogger(__name__)
router = APIRouter()
_client_message_adapter = TypeAdapter(ClientMessage)


def _step_status_for(event: TaskEvent) -> str:
    if event.status == TaskStatus.completed and event.success:
        return "completed"
    if event.status == TaskStatus.completed and not event.success:
        return "failed"
    return event.status.value


@router.websocket("/ws/run-conduit")
async def run_conduit_ws(websocket: WebSocket) -> None:
    """Accept a WS connection, multiplex flow runs over it.

    Builds a fresh :class:`Atelier` per connection so swapping
    ``executors["tool:hitl"]`` for a :class:`WsHitlExecutor` does not
    leak across sockets.
    """
    base_atelier: Atelier = get_atelier(websocket)  # type: ignore[arg-type]
    await websocket.accept()

    async def _send(payload: dict[str, Any]) -> None:
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.send_json(payload)

    broker = WebSocketBroker(send=_send)

    try:
        while True:
            try:
                raw = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            try:
                message = _client_message_adapter.validate_python(raw)
            except ValidationError as e:
                await _send(
                    {
                        "type": "error",
                        "message": f"invalid envelope: {e.errors()[0]['msg']}",
                    }
                )
                continue
            if isinstance(message, RunMessage):
                await _spawn_run(base_atelier, broker, message)
            elif isinstance(message, HitlAnswerMessage):
                try:
                    await broker.deliver_hitl_answer(
                        message.flow_id, dict(message.answers)
                    )
                except KeyError:
                    await _send(
                        {
                            "type": "error",
                            "flow_id": message.flow_id,
                            "message": "no flow registered for hitl_answer",
                        }
                    )
            elif isinstance(message, CancelMessage):
                broker.cancel(message.flow_id)
    finally:
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()


async def _spawn_run(
    base_atelier: Atelier,
    broker: WebSocketBroker,
    message: RunMessage,
) -> None:
    """Wire a per-flow Atelier and start the run task."""
    # Per-connection Atelier instance keeps executor swaps from leaking
    # across sockets (SPEC §10 / risk table).
    atelier = Atelier(base_dir=base_atelier.settings.atelier_dir)
    broker.register_flow(message.flow_id)
    atelier.executors["tool:hitl"] = WsHitlExecutor(
        broker=broker, flow_id=message.flow_id
    )

    async def _on_task_event(event: TaskEvent) -> None:
        await broker.send(
            {
                "type": "step_status",
                "flow_id": message.flow_id,
                "step": event.task,
                "status": _step_status_for(event),
            }
        )

    def _on_task_event_sync(event: TaskEvent) -> None:
        # Engine fires task events synchronously; schedule the async work.
        asyncio.create_task(_on_task_event(event))

    async def _run_and_report() -> None:
        try:
            await broker.send(
                {"type": "started", "flow_id": message.flow_id}
            )
            try:
                conduit = atelier.store.read_conduit(message.conduit_name)
            except FileNotFoundError as e:
                await broker.send(
                    {
                        "type": "flow_failed",
                        "flow_id": message.flow_id,
                        "error": str(e),
                    }
                )
                return
            try:
                flow_id = await atelier.engine.run(
                    conduit,
                    dict(message.inputs),
                    on_task_event=_on_task_event_sync,
                )
            except asyncio.CancelledError:
                await broker.send(
                    {
                        "type": "flow_failed",
                        "flow_id": message.flow_id,
                        "error": "cancelled",
                    }
                )
                raise
            except Exception as e:  # noqa: BLE001
                await broker.send(
                    {
                        "type": "flow_failed",
                        "flow_id": message.flow_id,
                        "error": str(e),
                    }
                )
                return

            for entry in atelier.store.read_logs(flow_id):
                await broker.send(
                    {
                        "type": "log",
                        "flow_id": message.flow_id,
                        "entry": entry.model_dump(mode="json"),
                    }
                )
            await broker.send(
                {"type": "flow_complete", "flow_id": message.flow_id}
            )
        finally:
            broker.unregister_flow(message.flow_id)

    task = asyncio.create_task(_run_and_report())
    broker.track_run(message.flow_id, task)
