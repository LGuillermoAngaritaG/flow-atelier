"""tool:bash executor — runs a shell command via asyncio subprocess."""
from __future__ import annotations

import asyncio
import os
import shutil
import signal

from flow_atelier.schemas.conduit import TaskDefinition
from flow_atelier.schemas.log import ExecutionResult
from flow_atelier.services.executor.base import ExecutorBase, FlowContext


class BashExecutor(ExecutorBase):
    """Executes ``tool:bash`` tasks via ``asyncio.create_subprocess_shell``.

    Trust model: ``{{inputs.x}}`` values are interpolated into the command
    string unescaped, so inputs are as trusted as the conduit author. A party
    who can only *supply* inputs (a scheduled job, a WS ``run`` message, a HITL
    answer) can inject shell metacharacters into an author's command. Authors
    should quote interpolations they don't control (e.g. ``"{{inputs.x}}"``).
    """

    @staticmethod
    def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
        """SIGKILL the whole process group led by ``proc``.

        Because the shell was started with ``start_new_session=True`` it leads
        its own group, so killing the group also kills the build/server/etc. it
        spawned — closing the orphaned-grandchild gap a bare ``proc.kill()``
        leaves. Falls back to killing just the shell if the group can't be
        resolved (already reaped) or signalled (race/permission), or on Windows
        where ``os.getpgid``/``os.killpg`` do not exist (AttributeError).

        :param proc: the shell subprocess to terminate together with its group.
        """
        if proc.pid is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    async def execute(
        self,
        task: TaskDefinition,
        resolved_command: str,
        context: FlowContext,
    ) -> ExecutionResult:
        """Run ``resolved_command`` as a shell subprocess.

        :param task: the task definition (unused beyond contract compliance)
        :param resolved_command: the shell command with templates resolved
        :param context: runtime :class:`FlowContext`, used for ``timeout``
        :returns: :class:`ExecutionResult` with stdout/stderr/exit code
        """
        # Run under bash explicitly, not create_subprocess_shell: that uses
        # /bin/sh (dash on Debian/Ubuntu/WSL) or cmd.exe on Windows, so
        # bashisms like `set -o pipefail` fail even though the tool is "bash".
        bash = shutil.which("bash")
        if bash is None:
            raise RuntimeError(
                "tool:bash requires `bash` on PATH (install git-bash/WSL on Windows)"
            )
        proc = await asyncio.create_subprocess_exec(
            bash,
            "-c",
            resolved_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(context.working_dir) if context.working_dir else None,
            # Own session/group: lets a timeout kill the shell *and* every
            # descendant it spawned (see _kill_process_group), instead of
            # leaving runaway grandchildren alive after the task gives up.
            start_new_session=True,
        )
        # Streams are pumped incrementally (not via communicate()) so a
        # timeout can kill the process and still keep the partial output:
        # cancelling communicate() discards data it already buffered.
        stdout_buf = bytearray()
        stderr_buf = bytearray()

        async def _pump(stream: asyncio.StreamReader, sink: bytearray) -> None:
            while chunk := await stream.read(65536):
                sink.extend(chunk)

        pumps = [
            asyncio.create_task(_pump(proc.stdout, stdout_buf)),
            asyncio.create_task(_pump(proc.stderr, stderr_buf)),
        ]
        try:
            await asyncio.wait_for(proc.wait(), timeout=context.timeout)
        except TimeoutError:
            self._kill_process_group(proc)
            # No proc.wait() here: its waiter only wakes once all pipes
            # close, and a grandchild that survived the group kill (e.g. one
            # that escaped into its own session) could hold them open. The
            # loop's child watcher reaps the shell.
            await asyncio.wait(pumps, timeout=0.5)
            for p in pumps:
                p.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            stdout = stdout_buf.decode("utf-8", errors="replace")
            stderr = stderr_buf.decode("utf-8", errors="replace")
            timeout_note = f"timeout after {context.timeout}s"
            return ExecutionResult(
                exit_code=124,
                stdout=stdout,
                stderr=f"{stderr}\n{timeout_note}" if stderr else timeout_note,
                output=stdout,
            )
        await asyncio.gather(*pumps)
        stdout = stdout_buf.decode("utf-8", errors="replace")
        stderr = stderr_buf.decode("utf-8", errors="replace")
        return ExecutionResult(
            exit_code=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            output=stdout,
        )
