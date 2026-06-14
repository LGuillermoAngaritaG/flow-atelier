"""Atelier facade: conduit CRUD + open-path."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings
from flow_atelier.schemas.api import CreateConduitInput, UpdateConduitInput


def _payload(name: str = "release_notes", description: str = "Release notes"):
    """Build a minimal CreateConduitInput payload for tests.

    :param name: conduit name to embed in the payload.
    :param description: conduit description to embed in the payload.
    """
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
def atelier(tmp_path, _isolate_global_atelier_dir):
    """Construct an Atelier instance rooted under tmp_path with an isolated global dir.

    :param tmp_path: pytest temp directory fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    global_dir: Path = _isolate_global_atelier_dir
    return Atelier(
        base_dir=tmp_path / ".atelier",
        settings=AtelierSettings(
            atelier_dir=tmp_path / ".atelier",
            global_atelier_dir=global_dir,
        ),
    )


# ----------------------------------------------------------- create


def test_create_conduit_persists_and_returns(atelier):
    """Verify create_conduit persists the conduit and lists it.

    :param atelier: Atelier facade fixture.
    """
    conduit = atelier.create_conduit(_payload())
    assert conduit.name == "release_notes"
    assert atelier.list_conduits() == ["release_notes"]


def test_create_conduit_rejects_collision(atelier):
    """Verify create_conduit raises FileExistsError on a name collision.

    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload())
    with pytest.raises(FileExistsError):
        atelier.create_conduit(_payload())


# ----------------------------------------------------------- update


def test_update_conduit_partial_description(atelier):
    """Verify update_conduit applies a partial description update.

    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload(description="old"))
    updated = atelier.update_conduit(
        "release_notes", UpdateConduitInput(description="new")
    )
    assert updated.description == "new"
    # Other fields preserved.
    assert updated.tasks[0].name == "echo"


def test_update_conduit_unknown_raises_not_found(atelier):
    """Verify update_conduit raises FileNotFoundError for unknown names.

    :param atelier: Atelier facade fixture.
    """
    with pytest.raises(FileNotFoundError):
        atelier.update_conduit(
            "ghost", UpdateConduitInput(description="anything")
        )


def test_update_conduit_rename_to_existing_is_rejected(atelier):
    """Renaming a conduit onto an existing name must not clobber it.

    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload(name="conduit_a", description="A"))
    atelier.create_conduit(_payload(name="conduit_b", description="B"))
    with pytest.raises(FileExistsError):
        atelier.update_conduit(
            "conduit_a", UpdateConduitInput(name="conduit_b")
        )
    # B is untouched and A still exists.
    assert atelier.store.read_conduit("conduit_b").description == "B"
    assert sorted(atelier.list_conduits()) == ["conduit_a", "conduit_b"]


def test_create_conduit_rejects_global_shadow(atelier):
    """Creating a project conduit whose name exists only globally is refused.

    :param atelier: Atelier facade fixture.
    """
    conduit = atelier.create_conduit(_payload(name="shared"))
    atelier.store.write_conduit_global(conduit)
    atelier.delete_conduit("shared")  # leave it only in the global store
    with pytest.raises(FileExistsError):
        atelier.create_conduit(_payload(name="shared"))


# ----------------------------------------------------------- delete


def test_delete_conduit_removes(atelier):
    """Verify delete_conduit removes an existing conduit.

    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload())
    assert atelier.delete_conduit("release_notes") is True
    assert atelier.list_conduits() == []


def test_delete_conduit_idempotent(atelier):
    """Verify delete_conduit returns False for an unknown conduit.

    :param atelier: Atelier facade fixture.
    """
    assert atelier.delete_conduit("ghost") is False


# ----------------------------------------------------------- open-path


def test_open_conduit_path_invokes_platform_opener(tmp_path, atelier):
    """Verify open_conduit_path spawns the platform-appropriate opener.

    :param tmp_path: pytest temp directory fixture.
    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload())
    run_path = tmp_path / "runs"
    run_path.mkdir()
    atelier.store.create_flow("release_notes", {"run_path": str(run_path)})
    with patch("subprocess.Popen") as popen:
        popen.return_value.poll.return_value = None
        ok = atelier.open_conduit_path(str(run_path))
    assert ok is True
    args = popen.call_args[0][0]
    if sys.platform == "darwin":
        assert args[0] == "open"
    elif sys.platform == "win32":
        assert args[0] == "explorer"
    else:
        assert args[0] == "xdg-open"


def test_open_conduit_path_returns_false_on_failure(tmp_path, atelier):
    """Verify open_conduit_path returns False when the opener fails.

    :param tmp_path: pytest temp directory fixture.
    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload())
    atelier.store.create_flow("release_notes", {"run_path": str(tmp_path)})
    with patch("subprocess.Popen", side_effect=FileNotFoundError("no opener")):
        ok = atelier.open_conduit_path(str(tmp_path))
    assert ok is False


def test_open_conduit_path_refuses_unknown_path(tmp_path, atelier):
    """Verify open_conduit_path refuses a path not recorded for any flow.

    :param tmp_path: pytest temp directory fixture.
    :param atelier: Atelier facade fixture.
    """
    atelier.create_conduit(_payload())
    with patch("subprocess.Popen") as popen:
        ok = atelier.open_conduit_path(str(tmp_path / "not-a-flow-run"))
    assert ok is False
    popen.assert_not_called()
