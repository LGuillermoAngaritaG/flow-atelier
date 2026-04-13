"""Facade: wires store + executors + engine and exposes the public API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.settings import AtelierSettings
from app.modules.engine import Engine, TaskEventCallback
from app.schemas.progress import Progress
from app.services.executor.bash import BashExecutor
from app.services.executor.conduit import ConduitExecutor
from app.services.executor.harness import ClaudeHarness, CodexHarness
from app.services.executor.hitl import HitlExecutor
from app.services.executor.prompt_sink import PromptSink, TerminalPromptSink
from app.services.store.filesystem import FilesystemStore


class Atelier:
    """Top-level facade for the flow-atelier engine.

    Wires :class:`FilesystemStore`, the tool/harness executors, and the DAG
    :class:`Engine` together and exposes the public API used by the CLI.

    :param settings: explicit :class:`AtelierSettings`; if omitted, loads
        from environment / ``.env``
    :param base_dir: convenience override for ``settings.atelier_dir``;
        ignored when ``settings`` is passed explicitly
    """

    def __init__(
        self,
        settings: AtelierSettings | None = None,
        base_dir: Path | str | None = None,
        prompt_sink: PromptSink | None = None,
    ) -> None:
        if settings is None:
            settings = (
                AtelierSettings(atelier_dir=Path(base_dir))
                if base_dir is not None
                else AtelierSettings()
            )
        self.settings = settings
        self.store = FilesystemStore(
            self.settings.atelier_dir,
            global_dir=self.settings.global_atelier_dir,
        )
        sink: PromptSink = prompt_sink if prompt_sink is not None else TerminalPromptSink()
        claude_launch = (
            self.settings.claude_launch_cmd or None
        )
        codex_launch = self.settings.codex_launch_cmd or None
        self.executors = {
            "tool:bash": BashExecutor(),
            "tool:hitl": HitlExecutor(),
            "tool:conduit": ConduitExecutor(),
            "harness:claude-code": ClaudeHarness(
                sink=sink,
                launch_cmd=claude_launch,
                done_marker=self.settings.done_marker,
            ),
            "harness:codex": CodexHarness(
                sink=sink,
                launch_cmd=codex_launch,
                done_marker=self.settings.done_marker,
            ),
        }
        self.engine = Engine(self.executors, self.store)

    async def run_conduit(
        self,
        name: str,
        inputs: dict[str, Any],
        on_task_event: TaskEventCallback | None = None,
    ) -> str:
        """Start a new flow for the named conduit.

        :param name: conduit name (must match a folder under ``conduits/``)
        :param inputs: conduit input map, keyed by input name
        :param on_task_event: optional callback invoked with a
            :class:`TaskEvent` after every task iteration finishes (success
            or failure). Exceptions raised by the callback are logged but
            do not affect the flow.
        :returns: the newly created flow id
        """
        conduit = self.store.read_conduit(name)
        return await self.engine.run(
            conduit, inputs, on_task_event=on_task_event
        )

    def get_status(self, flow_id: str) -> Progress:
        """Return the latest :class:`Progress` snapshot for ``flow_id``.

        :param flow_id: flow identifier
        :returns: current progress snapshot
        """
        return self.store.read_progress(flow_id)

    def list_conduits(self) -> list[str]:
        """List all available conduit names.

        :returns: sorted list of conduit names
        """
        return self.store.list_conduits()

    def list_flows(self, conduit_name: str | None = None) -> list[str]:
        """List flow ids, optionally filtered by conduit.

        :param conduit_name: restrict to flows of this conduit
        :returns: sorted list of flow ids
        """
        return self.store.list_flows(conduit_name)
