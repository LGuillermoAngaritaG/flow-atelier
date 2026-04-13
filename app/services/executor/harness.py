"""Harness executors — harness:claude-code and harness:codex over ACP.

Both harnesses speak the Agent Client Protocol (ACP) via Zed's adapter
binaries, launched through ``npx`` by default:

- ``harness:claude-code`` → ``@zed-industries/claude-code-acp``
- ``harness:codex``       → ``@zed-industries/codex-acp``

Non-interactive mode sends one prompt turn and returns whatever the agent
streams before ``stop_reason``. Interactive mode keeps the session open
and loops: after each turn, if the accumulated output has not contained
the done marker, the executor asks the :class:`PromptSink` for the user's
next message and sends another ``session/prompt``. The loop terminates
when the marker appears or when :attr:`MAX_INTERACTIVE_TURNS` is reached.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import acp
from acp.schema import (
    AgentMessageChunk,
    AllowedOutcome,
    DeniedOutcome,
    RequestPermissionResponse,
    TextContentBlock,
)

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.executor.base import ExecutorBase, FlowContext
from app.services.executor.prompt_sink import (
    PermissionOption,
    PromptSink,
    TerminalPromptSink,
)


DEFAULT_DONE_MARKER = "[ATELIER_DONE]"
MAX_INTERACTIVE_TURNS = 20

CLAUDE_ACP_LAUNCH = [
    "npx",
    "-y",
    "@zed-industries/claude-code-acp@0.16.2",
]
CODEX_ACP_LAUNCH = [
    "npx",
    "-y",
    "@zed-industries/codex-acp@0.11.1",
]


def build_interactive_suffix(marker: str) -> str:
    return (
        "\n\nWhen — and only when — you are completely finished answering, "
        f"output the exact token {marker} to signal completion. "
        "Do NOT echo or repeat the prompt back. Do NOT mention this "
        f"instruction in your answer. The token {marker} must appear only "
        "once, at the very end of your final response."
    )


class _BufferingClient:
    """ACP :class:`acp.Client` that buffers agent output and routes user I/O.

    Agent message chunks are appended to ``buffer`` and mirrored to the
    :class:`PromptSink`. Tool-permission requests are presented to the sink;
    the selected option id is returned as an :class:`AllowedOutcome`.

    The harness capabilities default to "no filesystem, no terminal" so the
    agent should not call the file/terminal methods — if it does, they raise
    :class:`NotImplementedError`.
    """

    def __init__(self, sink: PromptSink) -> None:
        self._sink = sink
        self.buffer: list[str] = []

    async def session_update(self, session_id: str, update, **kwargs) -> None:
        del session_id, kwargs
        if isinstance(update, AgentMessageChunk):
            content = update.content
            text = getattr(content, "text", None)
            if text:
                self.buffer.append(text)
                await self._sink.display(text)

    async def request_permission(
        self, options, session_id: str, tool_call, **kwargs
    ) -> RequestPermissionResponse:
        del session_id, kwargs
        if not options:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        sink_opts = [
            PermissionOption(id=o.option_id, label=o.name) for o in options
        ]
        summary = getattr(tool_call, "title", None) or "agent requests permission"
        chosen = await self._sink.request_permission(summary, sink_opts)
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", option_id=chosen)
        )

    # ---- capabilities we don't advertise: safe stubs ----
    async def write_text_file(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError("file write not supported by atelier harness")

    async def read_text_file(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError("file read not supported by atelier harness")

    async def create_terminal(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError("terminal not supported by atelier harness")

    async def terminal_output(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError

    async def release_terminal(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    async def wait_for_terminal_exit(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError

    async def kill_terminal(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    async def ext_method(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        del method, params
        return {}

    async def ext_notification(
        self, method: str, params: dict[str, Any]
    ) -> None:
        del method, params
        return None

    def on_connect(self, conn) -> None:
        self._conn = conn


class AcpHarnessExecutor(ExecutorBase):
    """Executor that drives an ACP agent subprocess.

    :param launch_cmd: argv to spawn the ACP agent (e.g.
        ``["npx", "-y", "@zed-industries/claude-code-acp"]``)
    :param sink: :class:`PromptSink` for user I/O and permission requests
    :param done_marker: substring that terminates an interactive loop
    """

    def __init__(
        self,
        launch_cmd: list[str],
        sink: PromptSink | None = None,
        done_marker: str | None = None,
    ) -> None:
        if not launch_cmd:
            raise ValueError("launch_cmd must not be empty")
        self.launch_cmd = list(launch_cmd)
        self.sink = sink if sink is not None else TerminalPromptSink()
        self.done_marker = done_marker or DEFAULT_DONE_MARKER

    async def execute(
        self,
        task: TaskDefinition,
        resolved_command: str,
        context: FlowContext,
    ) -> ExecutionResult:
        prompt_text = resolved_command
        if task.interactive:
            prompt_text = prompt_text + build_interactive_suffix(self.done_marker)

        cwd = str(Path.cwd())
        client = _BufferingClient(self.sink)

        try:
            return await asyncio.wait_for(
                self._drive_session(client, prompt_text, task.interactive, cwd),
                timeout=context.timeout,
            )
        except asyncio.TimeoutError:
            return ExecutionResult(
                exit_code=124,
                stdout="".join(client.buffer),
                stderr=f"harness timeout after {context.timeout}s",
                output="".join(client.buffer),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                exit_code=1,
                stdout="".join(client.buffer),
                stderr=f"{type(exc).__name__}: {exc}",
                output="".join(client.buffer),
            )

    async def _drive_session(
        self,
        client: _BufferingClient,
        initial_prompt: str,
        interactive: bool,
        cwd: str,
    ) -> ExecutionResult:
        cmd, *args = self.launch_cmd
        # Raise the per-line StreamReader limit well above asyncio's 64 KiB
        # default; Codex and similar harnesses emit large JSON-RPC frames
        # (tool results, planning output) that routinely exceed it.
        async with acp.spawn_agent_process(
            client,
            cmd,
            *args,
            cwd=cwd,
            transport_kwargs={"limit": 8 * 1024 * 1024},
        ) as (
            conn,
            _proc,
        ):
            await conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
            sess = await conn.new_session(cwd=cwd)

            if not interactive:
                return await self._run_single_turn(
                    conn, sess.session_id, initial_prompt, client
                )
            return await self._run_interactive(
                conn, sess.session_id, initial_prompt, client
            )

    async def _run_single_turn(
        self,
        conn,
        session_id: str,
        prompt_text: str,
        client: _BufferingClient,
    ) -> ExecutionResult:
        resp = await conn.prompt(
            prompt=[TextContentBlock(type="text", text=prompt_text)],
            session_id=session_id,
        )
        await self._drain_pending_notifications(client)
        return self._result_for_turn(client, resp.stop_reason)

    @staticmethod
    async def _drain_pending_notifications(client: _BufferingClient) -> None:
        """Wait for supervised notification handlers to finish.

        The ACP dispatcher runs each notification handler as a background
        task, so session_update handlers for the last few chunks may still
        be running when ``conn.prompt`` returns. We wait for the client's
        buffer to stabilize (no growth for two consecutive short yields)
        or until ``max_wait`` seconds have passed.
        """
        max_wait = 0.5
        stable_yields_required = 2
        deadline = asyncio.get_running_loop().time() + max_wait
        last_len = -1
        stable = 0
        while True:
            await asyncio.sleep(0.01)
            cur_len = len(client.buffer)
            if cur_len == last_len:
                stable += 1
                if stable >= stable_yields_required:
                    return
            else:
                stable = 0
                last_len = cur_len
            if asyncio.get_running_loop().time() >= deadline:
                return

    async def _run_interactive(
        self,
        conn,
        session_id: str,
        initial_prompt: str,
        client: _BufferingClient,
    ) -> ExecutionResult:
        next_prompt = initial_prompt
        last_stop = "end_turn"
        for _ in range(MAX_INTERACTIVE_TURNS):
            resp = await conn.prompt(
                prompt=[TextContentBlock(type="text", text=next_prompt)],
                session_id=session_id,
            )
            await self._drain_pending_notifications(client)
            last_stop = resp.stop_reason
            buffer_text = "".join(client.buffer)
            if self.done_marker in buffer_text:
                return ExecutionResult(
                    exit_code=0,
                    stdout=buffer_text,
                    stderr="",
                    output=buffer_text,
                )
            if resp.stop_reason not in ("end_turn", "max_tokens"):
                break
            try:
                user_reply = await self.sink.request_input(
                    "agent is waiting for your reply:"
                )
            except (EOFError, KeyboardInterrupt) as exc:
                return ExecutionResult(
                    exit_code=1,
                    stdout=buffer_text,
                    stderr=f"interactive input unavailable: {type(exc).__name__}",
                    output=buffer_text,
                )
            next_prompt = user_reply + build_interactive_suffix(self.done_marker)

        buffer_text = "".join(client.buffer)
        return ExecutionResult(
            exit_code=1,
            stdout=buffer_text,
            stderr=(
                f"interactive session ended without done marker "
                f"(last stop_reason={last_stop})"
            ),
            output=buffer_text,
        )

    @staticmethod
    def _result_for_turn(
        client: _BufferingClient, stop_reason: str
    ) -> ExecutionResult:
        output = "".join(client.buffer)
        if stop_reason in ("end_turn", "max_tokens"):
            return ExecutionResult(
                exit_code=0, stdout=output, stderr="", output=output
            )
        return ExecutionResult(
            exit_code=1,
            stdout=output,
            stderr=f"agent stopped with reason={stop_reason}",
            output=output,
        )


class ClaudeHarness(AcpHarnessExecutor):
    """`harness:claude-code` — drives ``@zed-industries/claude-code-acp``."""

    def __init__(
        self,
        sink: PromptSink | None = None,
        launch_cmd: list[str] | None = None,
        done_marker: str | None = None,
    ) -> None:
        super().__init__(
            launch_cmd=launch_cmd or list(CLAUDE_ACP_LAUNCH),
            sink=sink,
            done_marker=done_marker,
        )


class CodexHarness(AcpHarnessExecutor):
    """`harness:codex` — drives ``@zed-industries/codex-acp``."""

    def __init__(
        self,
        sink: PromptSink | None = None,
        launch_cmd: list[str] | None = None,
        done_marker: str | None = None,
    ) -> None:
        super().__init__(
            launch_cmd=launch_cmd or list(CODEX_ACP_LAUNCH),
            sink=sink,
            done_marker=done_marker,
        )
