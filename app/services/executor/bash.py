"""tool:bash executor — runs a shell command via asyncio subprocess."""
from __future__ import annotations

import asyncio

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.executor.base import ExecutorBase, FlowContext


class BashExecutor(ExecutorBase):
    """Executes ``tool:bash`` tasks via ``asyncio.create_subprocess_shell``."""

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
        proc = await asyncio.create_subprocess_shell(
            resolved_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=context.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecutionResult(
                exit_code=124,
                stdout="",
                stderr=f"timeout after {context.timeout}s",
                output="",
            )
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return ExecutionResult(
            exit_code=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            output=stdout,
        )
