"""Abstract store interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from app.schemas.conduit import Conduit
from app.schemas.log import LogEntry
from app.schemas.progress import Progress

ConduitSource = Literal["project", "global"]


class StoreBase(ABC):
    """File-I/O abstraction. Manages conduits, flows, logs, progress."""

    # --- conduits ---
    @abstractmethod
    def read_conduit(self, name: str) -> Conduit:
        """Load conduit ``name`` from the store.

        :param name: conduit name
        """
        ...

    @abstractmethod
    def list_conduits(self) -> list[str]:
        """Return all visible conduit names."""
        ...

    @abstractmethod
    def list_conduits_with_source(self) -> list[tuple[str, ConduitSource]]:
        """Return ``(name, source)`` pairs. Project shadows global on collision."""
        ...

    @abstractmethod
    def write_conduit(self, conduit: Conduit) -> None:
        """Persist ``conduit`` to the project store, overwriting if present.

        :param conduit: validated conduit to persist
        """
        ...

    @abstractmethod
    def write_conduit_global(self, conduit: Conduit) -> None:
        """Persist ``conduit`` to the global (user-level) store.

        :param conduit: validated conduit to persist
        :raises RuntimeError: if no global directory is available
        """
        ...

    @abstractmethod
    def conduit_source(self, name: str) -> ConduitSource:
        """Return whether ``name`` lives in the project or global store.

        :param name: conduit name
        :raises FileNotFoundError: if not found in either store
        """
        ...

    @abstractmethod
    def delete_conduit_global(self, name: str) -> bool:
        """Delete a global conduit. Returns False if it didn't exist.

        :param name: conduit name
        :returns: True if deleted, False if it didn't exist
        """
        ...

    @abstractmethod
    def delete_conduit(self, name: str) -> bool:
        """Delete a project-level conduit. Returns False if it didn't exist.

        :param name: conduit name
        """
        ...

    # --- flows ---
    @abstractmethod
    def create_flow(
        self,
        conduit_name: str,
        inputs: dict[str, Any],
        parent_flow_id: str | None = None,
    ) -> str:
        """Returns the new flow_id.

        :param conduit_name: conduit being run
        :param inputs: initial input map persisted with the flow
        :param parent_flow_id: optional parent flow for nested runs
        """

    @abstractmethod
    def list_flows(self, conduit_name: str | None = None) -> list[str]:
        """List top-level flow ids, optionally filtered by conduit.

        :param conduit_name: when set, only flows for this conduit are returned
        """
        ...

    # --- logs ---
    @abstractmethod
    async def append_log(self, flow_id: str, entry: LogEntry) -> None:
        """Append a log entry for ``flow_id``.

        :param flow_id: flow identifier
        :param entry: log entry to append
        """
        ...

    @abstractmethod
    def read_logs(self, flow_id: str) -> list[LogEntry]:
        """Return all log entries for ``flow_id`` in append order.

        :param flow_id: flow identifier
        :returns: list of :class:`LogEntry` — empty if the log is missing or empty
        """
        ...

    # --- progress ---
    @abstractmethod
    def write_progress(self, flow_id: str, progress: Progress) -> None:
        """Persist the progress snapshot for ``flow_id``.

        :param flow_id: flow identifier
        :param progress: progress snapshot to persist
        """
        ...

    @abstractmethod
    def read_progress(self, flow_id: str) -> Progress:
        """Return the ``Progress`` snapshot for ``flow_id``.

        :param flow_id: flow identifier
        """
        ...

    # --- outputs.yaml ---
    @abstractmethod
    def write_outputs(self, flow_id: str, outputs: dict[str, Any]) -> None:
        """Persist the per-task output map for ``flow_id``.

        :param flow_id: flow identifier
        :param outputs: mapping of task name to final output (``None`` for tasks
            that did not complete)
        """
        ...

    # --- input.yaml ---
    @abstractmethod
    def read_input(self, flow_id: str) -> dict[str, Any]:
        """Return the input map persisted for ``flow_id``.

        :param flow_id: flow identifier
        """
        ...

    @abstractmethod
    def append_input(self, flow_id: str, key: str, value: Any) -> None:
        """Set ``key=value`` in the flow's input map.

        :param flow_id: flow identifier
        :param key: input key to add or overwrite
        :param value: value to store under ``key``
        """
        ...
