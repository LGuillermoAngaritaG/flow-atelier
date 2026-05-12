"""Abstract executor contract and FlowContext."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.store.base import StoreBase


@dataclass
class FlowContext:
    """Runtime context handed to each executor invocation.

    ``run_nested_conduit`` lets ``tool:conduit`` call back into the engine.
    """

    flow_id: str
    store: StoreBase
    inputs: dict[str, Any]
    task_outputs: dict[str, str] = field(default_factory=dict)
    timeout: int = 3600
    show_steps: bool = True
    """Stream intermediate steps (thinking, tool calls, tool results) to the
    executor's :class:`PromptSink` as they happen. Independent of
    ``task.interactive`` (which gates raw message-chunk streaming)."""
    run_nested_conduit: Callable[[str, dict[str, Any], str], Awaitable[str]] | None = None
    """Callback: (conduit_name, inputs, parent_flow_id) -> child flow_id."""


class ExecutorBase(ABC):
    """Every tool/harness implements this interface."""

    @abstractmethod
    async def execute(
        self,
        task: TaskDefinition,
        resolved_command: str,
        context: FlowContext,
    ) -> ExecutionResult:
        """Run the task and return its ExecutionResult.

        ``resolved_command`` is the ``task`` field with templates already
        resolved by the engine.

        :param task: the task definition to execute.
        :param resolved_command: the task command with templates resolved.
        :param context: runtime :class:`FlowContext` for the execution.
        :returns: :class:`ExecutionResult` describing the outcome.
        """
