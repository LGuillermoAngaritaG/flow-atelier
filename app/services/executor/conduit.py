"""tool:conduit executor — runs another conduit as a nested flow."""
from __future__ import annotations

from typing import Any

from app.modules.templating import resolve
from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.executor.base import ExecutorBase, FlowContext


class ConduitExecutor(ExecutorBase):
    """Invokes another conduit by name via the engine callback.

    The task's ``inputs`` map (name -> template-string-or-value) is resolved
    against the parent's inputs and task outputs before dispatch.
    """

    async def execute(
        self,
        task: TaskDefinition,
        resolved_command: str,
        context: FlowContext,
    ) -> ExecutionResult:
        """Run another conduit as a nested flow.

        :param task: task whose ``inputs`` map is forwarded to the child
        :param resolved_command: name of the child conduit
        :param context: runtime :class:`FlowContext`; ``run_nested_conduit``
            is required
        :returns: :class:`ExecutionResult` whose ``output`` is the last
            successful log entry of the child flow
        """
        if context.run_nested_conduit is None:
            raise RuntimeError("ConduitExecutor requires context.run_nested_conduit")

        child_conduit_name = resolved_command.strip()
        child_inputs: dict[str, Any] = {}
        for key, raw in task.inputs.items():
            if isinstance(raw, str):
                child_inputs[key] = resolve(
                    raw, context.inputs, context.task_outputs
                )
            else:
                child_inputs[key] = raw

        child_flow_id = await context.run_nested_conduit(
            child_conduit_name, child_inputs, context.flow_id
        )

        child_progress = context.store.read_progress(child_flow_id)
        logs = context.store.read_logs(child_flow_id)
        last_output = ""
        for entry in reversed(logs):
            if entry.exit_code == 0 and entry.output:
                last_output = entry.output
                break

        status = child_progress.status.value
        exit_code = 0 if status == "completed" else 1
        return ExecutionResult(
            exit_code=exit_code,
            stdout=last_output,
            stderr="" if exit_code == 0 else f"nested conduit {status}",
            output=last_output,
        )
