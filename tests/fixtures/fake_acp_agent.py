"""Fake ACP agent used by harness executor tests.

Reads a scripted behavior from ``--script <json>`` on argv.

Script schema::

    {
        "turns": [
            {
                "chunks": ["text ", "more text"],
                "delay_before": 0.0,
                "stop": "end_turn",
                "ask_permission": null | {
                    "summary": "...",
                    "options": [{"id": "allow", "label": "Allow"}]
                }
            },
            ...
        ]
    }

Each call to ``prompt`` pops the next turn. If turns run out, the agent
returns ``stop_reason="end_turn"`` with no chunks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import acp
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AllowedOutcome,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PermissionOption as AcpPermissionOption,
    PromptCapabilities,
    PromptResponse,
    TextContentBlock,
    ToolCallUpdate,
)


class FakeAgent:
    def __init__(self, turns: list[dict[str, Any]]) -> None:
        self._turns = list(turns)
        self._conn: acp.Client | None = None

    def on_connect(self, conn: acp.Client) -> None:
        self._conn = conn

    async def initialize(
        self, protocol_version: int, client_capabilities=None, client_info=None, **kwargs
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=acp.PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                load_session=False,
                prompt_capabilities=PromptCapabilities(
                    audio=False, embedded_context=False, image=False
                ),
            ),
            agent_info=Implementation(name="fake-acp-agent", version="0.0.1"),
            auth_methods=[],
        )

    async def new_session(self, cwd: str, mcp_servers=None, **kwargs) -> NewSessionResponse:
        return NewSessionResponse(session_id="fake-session-1")

    async def prompt(self, prompt, session_id: str, **kwargs) -> PromptResponse:
        if not self._turns:
            return PromptResponse(stop_reason="end_turn")
        turn = self._turns.pop(0)

        delay = float(turn.get("delay_before", 0) or 0)
        if delay > 0:
            await asyncio.sleep(delay)

        assert self._conn is not None

        ask = turn.get("ask_permission")
        if ask:
            options = [
                AcpPermissionOption(
                    option_id=o["id"],
                    name=o["label"],
                    kind=o.get("kind", "allow_once"),
                )
                for o in ask["options"]
            ]
            tool_call = ToolCallUpdate(
                tool_call_id="tc-1",
                title=ask.get("summary", "permission"),
                kind="execute",
                status="pending",
            )
            resp = await self._conn.request_permission(
                options=options,
                session_id=session_id,
                tool_call=tool_call,
            )
            chosen_id = ""
            if isinstance(resp.outcome, AllowedOutcome):
                chosen_id = resp.outcome.option_id or ""
            await self._conn.session_update(
                session_id=session_id,
                update=AgentMessageChunk(
                    session_update="agent_message_chunk",
                    content=TextContentBlock(type="text", text=f"[perm:{chosen_id}]"),
                ),
            )

        for chunk_text in turn.get("chunks", []):
            await self._conn.session_update(
                session_id=session_id,
                update=AgentMessageChunk(
                    session_update="agent_message_chunk",
                    content=TextContentBlock(type="text", text=chunk_text),
                ),
            )

        return PromptResponse(stop_reason=turn.get("stop", "end_turn"))

    # ---- unused Agent methods: stub to satisfy protocol ----
    async def authenticate(self, method_id: str, **kwargs):
        return None

    async def load_session(self, *args, **kwargs):
        return None

    async def list_sessions(self, *args, **kwargs):
        raise NotImplementedError

    async def set_session_mode(self, *args, **kwargs):
        return None

    async def set_session_model(self, *args, **kwargs):
        return None

    async def set_config_option(self, *args, **kwargs):
        return None

    async def fork_session(self, *args, **kwargs):
        raise NotImplementedError

    async def resume_session(self, *args, **kwargs):
        raise NotImplementedError

    async def close_session(self, *args, **kwargs):
        return None

    async def ext_method(self, method: str, params):
        return {}

    async def ext_notification(self, method: str, params) -> None:
        return None


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    args = parser.parse_args()
    script = json.loads(args.script)
    agent = FakeAgent(turns=script.get("turns", []))
    await acp.run_agent(agent)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
