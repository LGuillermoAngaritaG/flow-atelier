"""Tests for Atelier.rerun_flow facade method."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.core.settings import AtelierSettings


@pytest.fixture
def atelier(tmp_path, _isolate_global_atelier_dir):
    """Construct an Atelier instance rooted under tmp_path.

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


def _seed_conduit(atelier: Atelier) -> None:
    """Write a one-task bash conduit with a defaulted input named ``msg``.

    :param atelier: Atelier facade fixture.
    """
    conduit_dir = atelier.store.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(
        "name: hello\n"
        "description: say hi\n"
        "inputs:\n"
        "  msg:\n"
        "    description: what to echo\n"
        "    default: hi\n"
        "tasks:\n"
        "  - greet:\n"
        "      description: greet\n"
        '      task: "echo {{ inputs.msg }}"\n'
        "      tool: tool:bash\n"
        "      depends_on: []\n"
    )


async def test_rerun_completed_flow_yields_new_id(atelier, tmp_path):
    """Rerun of a completed flow starts a fresh flow with a distinct id.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    _seed_conduit(atelier)
    src = await atelier.run_conduit("hello", {"msg": "one"}, working_dir=tmp_path)
    new_id = await atelier.rerun_flow(src, working_dir=tmp_path)
    assert new_id != src
    assert new_id in atelier.list_flows()


async def test_rerun_reuses_stored_inputs(atelier, tmp_path):
    """The new flow's input.yaml reuses the source flow's inputs verbatim.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    _seed_conduit(atelier)
    src = await atelier.run_conduit("hello", {"msg": "one"}, working_dir=tmp_path)
    new_id = await atelier.rerun_flow(src, working_dir=tmp_path)
    assert atelier.store.read_input(new_id).get("msg") == "one"


async def test_rerun_overrides_win_and_preserve_untouched(atelier, tmp_path):
    """Overrides replace only their keys; other stored inputs survive.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    _seed_conduit(atelier)
    src = await atelier.run_conduit("hello", {"msg": "one"}, working_dir=tmp_path)
    new_id = await atelier.rerun_flow(
        src, overrides={"msg": "two"}, working_dir=tmp_path
    )
    inputs = atelier.store.read_input(new_id)
    assert inputs.get("msg") == "two"
    assert inputs.get("run_path") == str(tmp_path)


async def test_rerun_carries_stored_run_path_into_working_dir(atelier, tmp_path):
    """With no working_dir given, rerun reuses the stored run_path.

    :param atelier: Atelier facade fixture.
    :param tmp_path: pytest temp directory fixture.
    """
    _seed_conduit(atelier)
    src = await atelier.run_conduit("hello", {"msg": "one"}, working_dir=tmp_path)
    new_id = await atelier.rerun_flow(src)
    assert atelier.store.read_input(new_id).get("run_path") == str(tmp_path)


async def test_rerun_unknown_flow_raises(atelier):
    """Rerunning a flow id with no stored conduit/flow raises FileNotFoundError.

    :param atelier: Atelier facade fixture.
    """
    with pytest.raises(FileNotFoundError):
        await atelier.rerun_flow("20260101_abcdef12_nonexistent")
