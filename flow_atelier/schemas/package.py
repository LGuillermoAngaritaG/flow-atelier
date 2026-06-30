"""Package manifest schema for ``atelier add``."""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

# Manifest name and each conduit entry become a single filesystem path
# component, so they must reject separators and dot-traversal on install.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class PackageManifest(BaseModel):
    """A conduit package's ``atelier-package.yaml`` (conduits).

    Schedules are intentionally absent (D7): a shipped schedule carries
    machine-specific state and cannot travel, so the installer never reads one.
    """

    name: str
    version: int = 1
    conduits: list[str] = []

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Reject a package name that isn't a safe path component.

        :param value: the manifest name.
        :returns: the name unchanged when safe.
        """
        if not _SAFE_NAME_RE.match(value):
            raise ValueError(f"unsafe package name: {value!r}")
        return value

    @field_validator("conduits")
    @classmethod
    def _validate_entries(cls, values: list[str]) -> list[str]:
        """Reject conduit entries that aren't safe path components.

        :param values: declared conduit directory names.
        :returns: the list unchanged when every entry is safe.
        """
        for v in values:
            if not _SAFE_NAME_RE.match(v):
                raise ValueError(f"unsafe package entry: {v!r}")
        return values
