"""Atelier facade: conduit CRUD + open-path."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from app.core.atelier import Atelier
from app.schemas.api import CreateConduitInput, UpdateConduitInput


def _payload(name: str = "release_notes", description: str = "Release notes"):
    return CreateConduitInput.model_validate(
        {
            "name": name,
            "description": description,
            "tasks": [
                {
                    "name": "echo",
                    "description": "echo",
                    "task": "echo hi",
                    "tool": "tool:bash",
                    "depends_on": [],
                }
            ],
        }
    )


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


# ----------------------------------------------------------- create


def test_create_conduit_persists_and_returns(atelier):
    conduit = atelier.create_conduit(_payload())
    assert conduit.name == "release_notes"
    assert atelier.list_conduits() == ["release_notes"]


def test_create_conduit_rejects_collision(atelier):
    atelier.create_conduit(_payload())
    with pytest.raises(FileExistsError):
        atelier.create_conduit(_payload())


# ----------------------------------------------------------- update


def test_update_conduit_partial_description(atelier):
    atelier.create_conduit(_payload(description="old"))
    updated = atelier.update_conduit(
        "release_notes", UpdateConduitInput(description="new")
    )
    assert updated.description == "new"
    # Other fields preserved.
    assert updated.tasks[0].name == "echo"


def test_update_conduit_unknown_raises_not_found(atelier):
    with pytest.raises(FileNotFoundError):
        atelier.update_conduit(
            "ghost", UpdateConduitInput(description="anything")
        )


# ----------------------------------------------------------- delete


def test_delete_conduit_removes(atelier):
    atelier.create_conduit(_payload())
    assert atelier.delete_conduit("release_notes") is True
    assert atelier.list_conduits() == []


def test_delete_conduit_idempotent(atelier):
    assert atelier.delete_conduit("ghost") is False


# ----------------------------------------------------------- open-path


def test_open_conduit_path_invokes_platform_opener(tmp_path, atelier):
    atelier.create_conduit(_payload())
    run_path = tmp_path / "runs"
    run_path.mkdir()
    with patch("subprocess.Popen") as popen:
        popen.return_value.poll.return_value = None
        ok = atelier.open_conduit_path("release_notes", str(run_path))
    assert ok is True
    args = popen.call_args[0][0]
    if sys.platform == "darwin":
        assert args[0] == "open"
    elif sys.platform == "win32":
        assert args[0] == "explorer"
    else:
        assert args[0] == "xdg-open"


def test_open_conduit_path_returns_false_on_failure(tmp_path, atelier):
    atelier.create_conduit(_payload())
    with patch("subprocess.Popen", side_effect=FileNotFoundError("no opener")):
        ok = atelier.open_conduit_path("release_notes", str(tmp_path))
    assert ok is False
