"""Facade: wires store + executors + engine and exposes the public API."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.settings import AtelierSettings
from app.modules.engine import Engine, FlowStartedCallback, TaskEventCallback
from app.schemas.api import CreateConduitInput, UpdateConduitInput
from app.schemas.conduit import Conduit
from app.schemas.progress import Progress
from app.services.executor.bash import BashExecutor
from app.services.executor.conduit import ConduitExecutor
from app.services.executor.harness import (
    ClaudeHarness,
    CodexHarness,
    CopilotHarness,
    CursorHarness,
    OpencodeHarness,
)
from app.services.executor.hitl import HitlExecutor
from app.services.executor.prompt_sink import PromptSink, TerminalPromptSink
from app.services.store.filesystem import FilesystemStore


logger = logging.getLogger(__name__)


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
        opencode_launch = self.settings.opencode_launch_cmd or None
        copilot_launch = self.settings.copilot_launch_cmd or None
        cursor_launch = self.settings.cursor_launch_cmd or None
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
            "harness:opencode": OpencodeHarness(
                sink=sink,
                launch_cmd=opencode_launch,
                done_marker=self.settings.done_marker,
            ),
            "harness:copilot": CopilotHarness(
                sink=sink,
                launch_cmd=copilot_launch,
                done_marker=self.settings.done_marker,
            ),
            "harness:cursor": CursorHarness(
                sink=sink,
                launch_cmd=cursor_launch,
                done_marker=self.settings.done_marker,
            ),
        }
        self.engine = Engine(self.executors, self.store)

    async def run_conduit(
        self,
        name: str,
        inputs: dict[str, Any],
        on_task_event: TaskEventCallback | None = None,
        on_flow_started: FlowStartedCallback | None = None,
    ) -> str:
        """Start a new flow for the named conduit.

        :param name: conduit name (must match a folder under ``conduits/``)
        :param inputs: conduit input map, keyed by input name
        :param on_task_event: optional callback invoked with a
            :class:`TaskEvent` after every task iteration finishes (success
            or failure). Exceptions raised by the callback are logged but
            do not affect the flow.
        :param on_flow_started: optional callback invoked once with the
            new flow id, before any task runs. Lets the caller record the
            id and surface it on failure as well as on success.
        :returns: the newly created flow id
        """
        conduit = self.store.read_conduit(name)
        return await self.engine.run(
            conduit,
            inputs,
            on_task_event=on_task_event,
            on_flow_started=on_flow_started,
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

    # ------------------------------------------------------------------ CRUD

    def create_conduit(self, payload: CreateConduitInput) -> Conduit:
        """Persist a new conduit; raise if one with that name already exists.

        :param payload: validated :class:`CreateConduitInput`
        :returns: the persisted :class:`Conduit`
        :raises FileExistsError: if a project conduit with that name exists
        """
        existing = self.store.base_dir / "conduits" / payload.name
        if existing.exists():
            raise FileExistsError(f"conduit already exists: {payload.name}")
        conduit = Conduit.model_validate(payload.model_dump())
        self.store.write_conduit(conduit)
        return conduit

    def update_conduit(
        self, name: str, payload: UpdateConduitInput
    ) -> Conduit:
        """Apply a partial update to an existing conduit.

        :param name: conduit to modify
        :param payload: subset of fields to overwrite
        :returns: the updated :class:`Conduit`
        :raises FileNotFoundError: if the conduit doesn't exist
        """
        existing = self.store.read_conduit(name)
        merged = existing.model_dump()
        for key, value in payload.model_dump(exclude_none=True).items():
            merged[key] = value
        merged["name"] = merged.get("name") or name
        updated = Conduit.model_validate(merged)
        self.store.write_conduit(updated)
        if updated.name != name:
            # Rename: drop the old folder.
            self.store.delete_conduit(name)
        return updated

    def delete_conduit(self, name: str) -> bool:
        """Remove a project-level conduit.

        :param name: conduit name
        :returns: True if it existed and was deleted, False otherwise
        """
        return self.store.delete_conduit(name)

    def open_conduit_path(self, conduit_name: str, run_path: str) -> bool:
        """Reveal ``run_path`` in the host's file explorer.

        :param conduit_name: conduit context (not used by the OS opener,
            kept for API symmetry with the frontend contract)
        :param run_path: absolute path to open
        :returns: True if the platform opener was launched, False otherwise
        """
        del conduit_name
        cmd: list[str]
        if sys.platform == "darwin":
            cmd = ["open", run_path]
        elif sys.platform == "win32":
            cmd = ["explorer", run_path]
        else:
            cmd = ["xdg-open", run_path]
        try:
            subprocess.Popen(cmd)
        except (FileNotFoundError, OSError) as e:
            logger.warning("open_conduit_path failed: %s", e)
            return False
        return True
