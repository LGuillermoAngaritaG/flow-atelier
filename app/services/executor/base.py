"""Abstract executor contract and FlowContext."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.schemas.conduit import TaskDefinition
from app.schemas.log import ExecutionResult
from app.services.store.base import StoreBase


@dataclass
class ChannelExecutionContext:
    """Per-flow state injected when a faucet conduit is driven by a channel.

    Consumed by ``AcpHarnessExecutor`` (for resume) and ``tool:reply``
    (for addressing). Lives on :class:`FlowContext` so non-channel paths
    can ignore it entirely.

    :param faucet: when ``True``, harnesses run a single ACP turn and skip
        the ``[ATELIER_DONE]`` marker loop regardless of ``task.interactive``
    :param resume_session_ids: ``{task_name: session_id}`` from the channel
        session store; harnesses use ``load_session`` when their entry exists
    :param on_session_minted: callback ``(task_name, session_id)`` invoked
        once per harness turn so the registry can persist the id; receives
        the resumed id when one was provided, otherwise the freshly minted id
    :param channel: configured channel name
    :param session_key: per-sender key (e.g. ``str(chat_id)``)
    :param address: opaque payload the originating adapter needs to reply
    """

    faucet: bool = False
    resume_session_ids: dict[str, str] = field(default_factory=dict)
    on_session_minted: Callable[[str, str], None] | None = None
    channel: str = ""
    session_key: str = ""
    address: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowContext:
    """Runtime context handed to each executor invocation.

    ``run_nested_conduit`` lets ``tool:conduit`` call back into the engine.
    ``channel_context`` is set only when the flow was triggered by a channel
    adapter feeding a faucet conduit.
    """

    flow_id: str
    store: StoreBase
    inputs: dict[str, Any]
    task_outputs: dict[str, str] = field(default_factory=dict)
    timeout: int = 3600
    run_nested_conduit: Callable[[str, dict[str, Any], str], Awaitable[str]] | None = None
    """Callback: (conduit_name, inputs, parent_flow_id) -> child flow_id."""
    channel_context: ChannelExecutionContext | None = None


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
        """
