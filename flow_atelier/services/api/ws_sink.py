"""WebSocket-driven PromptSink for real-time step streaming.

Replaces :class:`TerminalPromptSink` for connections served over the
WebSocket endpoint: ``display_step`` forwards intermediate steps as
``step`` envelopes through the broker as they arrive from the harness
executor, rather than writing them to the terminal.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from flow_atelier.modules.engine import current_flow_id, current_task
from flow_atelier.services.api.ws_manager import WebSocketBroker

if TYPE_CHECKING:
    from flow_atelier.schemas.log import IntermediateStep


class WsPromptSink:
    """:class:`PromptSink` that streams intermediate steps over WebSocket.

    :param broker: per-connection broker used to send envelopes
    :param flow_id: flow this sink instance is bound to
    """

    def __init__(self, broker: WebSocketBroker, flow_id: str) -> None:
        """Bind the sink to a broker and a specific flow.

        :param broker: per-connection broker used to send envelopes
        :param flow_id: flow this sink instance is bound to
        """
        self._broker = broker
        self._flow_id = flow_id

    async def display(self, text: str) -> None:
        """Stream one agent prose chunk as an ``agent_message`` envelope.

        Only interactive tasks reach here (the harness mirrors chunks to the
        sink when ``stream_messages`` is on), so this is the live view of the
        question the agent is asking before it hands the turn back.

        :param text: agent text chunk to forward.
        """
        await self._broker.send(
            {
                "type": "agent_message",
                "flow_id": current_flow_id(self._flow_id),
                "task": current_task(""),
                "text": text,
            }
        )

    async def start_agent_turn(self, label: str = "agent") -> None:
        """No-op for WebSocket runs.

        :param label: turn label (ignored).
        """

    async def request_input(self, prompt: str) -> str:
        """Ask the client for the next turn and wait for the matching answer.

        The request carries an opaque id so two interactive tasks prompting
        at once can't consume each other's replies. The pending entry is
        dropped on the way out whatever happens — answered, cancelled, or
        failed — so a late answer can never satisfy a later prompt.

        :param prompt: prompt label shown to the user.
        :returns: the user's reply.
        """
        flow_id = current_flow_id(self._flow_id)
        request_id, future = self._broker.open_agent_input_request(flow_id)
        try:
            await self._broker.send(
                {
                    "type": "agent_input_request",
                    "flow_id": flow_id,
                    "task": current_task(""),
                    "request_id": request_id,
                    "prompt": prompt,
                }
            )
            return await future
        finally:
            self._broker.close_agent_input_request(flow_id, request_id)

    async def display_step(self, step: IntermediateStep) -> None:
        """Forward an intermediate step as a ``step`` envelope over WebSocket.

        Reads the current task name from the engine's contextvar so that
        concurrent tasks don't clobber each other.

        :param step: the :class:`IntermediateStep` to forward.
        """
        await self._broker.send(
            {
                "type": "step",
                "flow_id": current_flow_id(self._flow_id),
                "task": current_task(""),
                "step": step.model_dump(mode="json"),
            }
        )
