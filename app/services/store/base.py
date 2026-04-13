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
    def read_conduit(self, name: str) -> Conduit: ...

    @abstractmethod
    def list_conduits(self) -> list[str]: ...

    @abstractmethod
    def list_conduits_with_source(self) -> list[tuple[str, ConduitSource]]:
        """Return ``(name, source)`` pairs. Project shadows global on collision."""
        ...

    # --- flows ---
    @abstractmethod
    def create_flow(
        self,
        conduit_name: str,
        inputs: dict[str, Any],
        parent_flow_id: str | None = None,
    ) -> str:
        """Returns the new flow_id."""

    @abstractmethod
    def list_flows(self, conduit_name: str | None = None) -> list[str]: ...

    # --- logs ---
    @abstractmethod
    async def append_log(self, flow_id: str, entry: LogEntry) -> None: ...

    @abstractmethod
    def read_logs(self, flow_id: str) -> list[LogEntry]:
        """Return all log entries for ``flow_id`` in append order.

        :param flow_id: flow identifier
        :returns: list of :class:`LogEntry` — empty if the log is missing or empty
        """
        ...

    # --- progress ---
    @abstractmethod
    def write_progress(self, flow_id: str, progress: Progress) -> None: ...

    @abstractmethod
    def read_progress(self, flow_id: str) -> Progress: ...

    # --- input.yaml ---
    @abstractmethod
    def read_input(self, flow_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def append_input(self, flow_id: str, key: str, value: Any) -> None: ...
