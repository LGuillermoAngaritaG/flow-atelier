"""Harness executors — five ACP-speaking coding agents.

Each harness is a thin :class:`AcpHarnessExecutor` subclass differing only
in its ``launch_cmd``. Each reuses the host CLI's own config and auth.

- ``harness:claude-code`` → ``@zed-industries/claude-code-acp`` via ``npx``
- ``harness:codex``       → ``@zed-industries/codex-acp`` via ``npx``
- ``harness:opencode``    → ``opencode acp`` (native ACP)
- ``harness:copilot``     → ``copilot --acp`` (GitHub Copilot CLI, native ACP)
- ``harness:cursor``      → ``@blowmage/cursor-agent-acp`` via ``npx``

Non-interactive mode sends one prompt turn and returns whatever the agent
streams before ``stop_reason``. Interactive mode keeps the session open
and loops: after each turn, if the accumulated output has not contained
the done marker, the executor asks the :class:`PromptSink` for the user's
next message and sends another ``session/prompt``. The loop terminates
when the marker appears or when :attr:`MAX_INTERACTIVE_TURNS` is reached.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import acp
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    DeniedOutcome,
    RequestPermissionResponse,
    SessionModeState,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult, IntermediateStep, StepKind
from app.services.executor.base import ExecutorBase, FlowContext
from app.services.executor.prompt_sink import (
    PromptSink,
    TerminalPromptSink,
)


logger = logging.getLogger(__name__)


DEFAULT_DONE_MARKER = "[ATELIER_DONE]"
MAX_INTERACTIVE_TURNS = 20

# Mode-id keyword tiers in descending permissiveness. Each ACP agent
# advertises its own mode ids; we pick the most permissive one available so
# the agent never has to ask for tool permission. Keyword matched against
# ``id`` case-insensitively.
PERMISSIVE_MODE_KEYWORDS: tuple[str, ...] = (
    "bypass",      # claude-code-acp's bypassPermissions
    "yolo",
    "danger",      # codex-acp's danger-full-access family
    "full-auto",
    "full_auto",
    "accept",      # claude-code-acp's acceptEdits (weaker, but still skips edit prompts)
    "auto",
)


def _pick_permissive_mode(state: SessionModeState | None) -> str | None:
    """Return the most permissive mode id from ``state``, or ``None``.

    Walks :data:`PERMISSIVE_MODE_KEYWORDS` and returns the first
    available mode whose ``id`` contains a keyword (case-insensitive).
    """
    if state is None or not state.available_modes:
        return None
    available = state.available_modes
    for keyword in PERMISSIVE_MODE_KEYWORDS:
        for mode in available:
            if keyword in mode.id.lower():
                return mode.id
    return None

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
OPENCODE_ACP_LAUNCH = ["opencode", "acp"]
COPILOT_ACP_LAUNCH = ["copilot", "--acp"]
CURSOR_ACP_LAUNCH = [
    "npx",
    "-y",
    "@blowmage/cursor-agent-acp@0.7.1",
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

    :param sink: surface for permission requests and (when enabled) live
        chunk / step streaming
    :param stream_messages: when ``True`` (interactive turns), agent message
        chunks are mirrored to ``sink.display`` as they arrive so the user
        can follow the agent before deciding their next reply. When
        ``False`` (single-turn / non-interactive), chunks are only buffered
        for the result — the caller renders them once when the turn ends,
        avoiding double-rendering of the same text.
    :param stream_steps: when ``True``, intermediate steps (thinking, tool
        calls, tool results) are mirrored to ``sink.display_step`` as they
        arrive. Independent of ``stream_messages`` so non-interactive runs
        can surface tool/thinking activity live without dumping the agent's
        full prose mid-flow.
    """

    def __init__(
        self,
        sink: PromptSink,
        stream_messages: bool = False,
        stream_steps: bool = False,
        done_marker: str = DEFAULT_DONE_MARKER,
    ) -> None:
        self._sink = sink
        self._stream_messages = stream_messages
        self._stream_steps = stream_steps
        self._done_marker = done_marker
        self.buffer: list[str] = []
        self.steps: list[IntermediateStep] = []

    async def session_update(self, session_id: str, update, **kwargs) -> None:
        del session_id, kwargs
        if isinstance(update, AgentMessageChunk):
            content = update.content
            text = getattr(content, "text", None)
            if text:
                self.buffer.append(text)
                if self._stream_messages:
                    await self._sink.display(text.replace(self._done_marker, ""))
        elif isinstance(update, AgentThoughtChunk):
            text = getattr(update.content, "text", "") or ""
            step = IntermediateStep(kind=StepKind.thinking, text=text)
            self.steps.append(step)
            if self._stream_steps and hasattr(self._sink, "display_step"):
                await self._sink.display_step(step)
        elif isinstance(update, ToolCallStart):
            step = IntermediateStep(
                kind=StepKind.tool_call,
                tool_call_id=update.tool_call_id,
                tool_name=update.title,
                tool_kind=update.kind or "",
                tool_status=update.status or "",
                tool_input=str(update.raw_input)[:500] if update.raw_input else "",
                locations=[loc.path for loc in (update.locations or [])],
            )
            self.steps.append(step)
            if self._stream_steps and hasattr(self._sink, "display_step"):
                await self._sink.display_step(step)
        elif isinstance(update, ToolCallProgress):
            if update.status in ("completed", "failed"):
                step = IntermediateStep(
                    kind=StepKind.tool_result,
                    tool_call_id=update.tool_call_id,
                    tool_status=update.status or "",
                    tool_output=str(update.raw_output)[:500] if update.raw_output else "",
                )
                self.steps.append(step)
                if self._stream_steps and hasattr(self._sink, "display_step"):
                    await self._sink.display_step(step)

    async def request_permission(
        self, options, session_id: str, tool_call, **kwargs
    ) -> RequestPermissionResponse:
        # Backstop for any agent that still asks despite the permissive
        # session mode: silently pick the most permissive allow option.
        # Tool activity is still surfaced to the user via display_step.
        del session_id, tool_call, kwargs
        if not options:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        chosen = (
            next((o for o in options if (o.kind or "") == "allow_always"), None)
            or next((o for o in options if (o.kind or "") == "allow_once"), None)
            or next((o for o in options if (o.kind or "").startswith("allow")), None)
        )
        if chosen is None:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", option_id=chosen.option_id)
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
        client = _BufferingClient(
            self.sink,
            stream_messages=task.interactive,
            stream_steps=(task.interactive or context.show_steps),
            done_marker=self.done_marker,
        )

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
                steps=client.steps,
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                exit_code=1,
                stdout="".join(client.buffer),
                stderr=f"{type(exc).__name__}: {exc}",
                output="".join(client.buffer),
                steps=client.steps,
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
            await self._maybe_switch_to_permissive_mode(conn, sess)

            if not interactive:
                return await self._run_single_turn(
                    conn, sess.session_id, initial_prompt, client
                )
            return await self._run_interactive(
                conn, sess.session_id, initial_prompt, client
            )

    @staticmethod
    async def _maybe_switch_to_permissive_mode(conn, sess) -> None:
        """Switch the session into the most permissive mode the agent offers.

        ACP session modes are the upstream "skip permissions" knob (see
        https://agentclientprotocol.com/protocol/session-modes). Each agent
        advertises its own mode ids (e.g. claude-code-acp's
        ``bypassPermissions``, codex-acp's ``danger-full-access``) under
        ``new_session.modes``. We pick the most permissive one and switch
        before the first prompt so the agent never has to call
        ``session/request_permission``. A bad mode switch is non-fatal —
        the auto-approve backstop in :meth:`_BufferingClient.request_permission`
        still catches any residual prompts.
        """
        modes = getattr(sess, "modes", None)
        picked = _pick_permissive_mode(modes)
        if picked is None or picked == modes.current_mode_id:
            return
        try:
            await conn.set_session_mode(mode_id=picked, session_id=sess.session_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("set_session_mode(%s) failed: %s", picked, exc)

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
        # Sinks that don't render visually (e.g. API/queue transports)
        # may omit start_agent_turn; only call it if implemented.
        start_turn = getattr(self.sink, "start_agent_turn", None)
        for _ in range(MAX_INTERACTIVE_TURNS):
            if start_turn is not None:
                await start_turn()
            prev_buffer_len = len(client.buffer)
            resp = await conn.prompt(
                prompt=[TextContentBlock(type="text", text=next_prompt)],
                session_id=session_id,
            )
            await self._drain_pending_notifications(client)
            last_stop = resp.stop_reason
            buffer_text = "".join(client.buffer)
            if self.done_marker in buffer_text:
                # Strip the protocol sentinel from anything we hand back to
                # the user — it's an internal coordination marker, not content.
                cleaned = buffer_text.replace(self.done_marker, "").rstrip()
                last_turn = (
                    "".join(client.buffer[prev_buffer_len:])
                    .replace(self.done_marker, "")
                    .rstrip()
                )
                return ExecutionResult(
                    exit_code=0,
                    stdout=cleaned,
                    stderr="",
                    output=cleaned,
                    last_turn_output=last_turn,
                    steps=client.steps,
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
                    steps=client.steps,
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
            steps=client.steps,
        )

    @staticmethod
    def _result_for_turn(
        client: _BufferingClient, stop_reason: str
    ) -> ExecutionResult:
        output = "".join(client.buffer)
        if stop_reason in ("end_turn", "max_tokens"):
            return ExecutionResult(
                exit_code=0, stdout=output, stderr="", output=output,
                steps=client.steps,
            )
        return ExecutionResult(
            exit_code=1,
            stdout=output,
            stderr=f"agent stopped with reason={stop_reason}",
            output=output,
            steps=client.steps,
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


class OpencodeHarness(AcpHarnessExecutor):
    """`harness:opencode` — drives ``opencode acp`` (native ACP)."""

    def __init__(
        self,
        sink: PromptSink | None = None,
        launch_cmd: list[str] | None = None,
        done_marker: str | None = None,
    ) -> None:
        super().__init__(
            launch_cmd=launch_cmd or list(OPENCODE_ACP_LAUNCH),
            sink=sink,
            done_marker=done_marker,
        )


class CopilotHarness(AcpHarnessExecutor):
    """`harness:copilot` — drives ``copilot --acp`` (GitHub Copilot CLI)."""

    def __init__(
        self,
        sink: PromptSink | None = None,
        launch_cmd: list[str] | None = None,
        done_marker: str | None = None,
    ) -> None:
        super().__init__(
            launch_cmd=launch_cmd or list(COPILOT_ACP_LAUNCH),
            sink=sink,
            done_marker=done_marker,
        )


class CursorHarness(AcpHarnessExecutor):
    """`harness:cursor` — drives the ``@blowmage/cursor-agent-acp`` adapter via npx."""

    def __init__(
        self,
        sink: PromptSink | None = None,
        launch_cmd: list[str] | None = None,
        done_marker: str | None = None,
    ) -> None:
        super().__init__(
            launch_cmd=launch_cmd or list(CURSOR_ACP_LAUNCH),
            sink=sink,
            done_marker=done_marker,
        )
