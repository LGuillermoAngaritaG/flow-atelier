"""CLI tests for `atelier rm` and `atelier prune` (flow-run retention)."""
import json
import os

import pytest
from typer.testing import CliRunner

from flow_atelier.cli import app


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Provide an isolated working dir with a `.atelier/flows` tree.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    (tmp_path / ".atelier" / "flows").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_") and k not in (
            "ATELIER_GLOBAL_ATELIER_DIR",
            "ATELIER_NO_UPDATE_CHECK",
        ):
            monkeypatch.delenv(k, raising=False)
    return tmp_path


def _make_flow(workdir, flow_id, status="completed"):
    """Create a flow dir on disk with a progress.json of the given status.

    :param workdir: working directory path.
    :param flow_id: full flow id (``YYYYMMDD_<uuid8>_<conduit>``).
    :param status: FlowStatus value to persist (default ``completed``).
    :returns: the flow's directory Path.
    """
    flow_dir = workdir / ".atelier" / "flows" / flow_id
    flow_dir.mkdir(parents=True)
    (flow_dir / "progress.json").write_text(
        json.dumps(
            {
                "status": status,
                "current_tasks": [],
                "tasks": {},
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": None,
            }
        )
    )
    return flow_dir


def test_prune_older_than_selects_old_only(workdir):
    """`prune --older-than` deletes ids older than the cutoff, keeps newer.

    :param workdir: isolated working directory fixture.
    """
    old = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    new = _make_flow(workdir, "20990101_bbbbbbbb_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--older-than", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert not old.exists()
    assert new.exists()


def test_prune_keep_retains_most_recent(workdir):
    """`prune --keep N` retains the N most-recent ids and deletes the rest.

    :param workdir: isolated working directory fixture.
    """
    a = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    b = _make_flow(workdir, "20210101_bbbbbbbb_hello")
    c = _make_flow(workdir, "20220101_cccccccc_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--keep", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert not a.exists()
    assert not b.exists()
    assert c.exists()


def test_prune_skips_running_without_force(workdir):
    """`prune` never deletes a running flow unless --force is given.

    :param workdir: isolated working directory fixture.
    """
    running = _make_flow(workdir, "20200101_aaaaaaaa_hello", status="running")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--older-than", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert running.exists()

    forced = runner.invoke(app, ["prune", "--older-than", "1", "--force", "--yes"])
    assert forced.exit_code == 0, forced.output
    assert not running.exists()


def test_prune_bare_refuses(workdir):
    """A bare `prune` with no selector refuses and deletes nothing.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune"])
    assert result.exit_code != 0
    assert "refusing to prune" in result.output
    assert f.exists()


def test_prune_declined_confirm_keeps_dir(workdir):
    """Declining the prune confirmation leaves the flow dir intact.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--older-than", "1"], input="n\n")
    assert result.exit_code != 0
    assert f.exists()


def test_prune_json_without_yes_is_dry_run(workdir):
    """`prune --json` without --yes previews and deletes nothing.

    JSON mode is non-interactive and must not delete without explicit --yes.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--older-than", "1", "--json"])
    assert result.exit_code == 0, result.output
    assert f.exists()
    payload = json.loads(result.output)
    assert payload["deleted"] == []
    assert payload["would_delete"] == ["20200101_aaaaaaaa_hello"]


def test_prune_json_with_yes_deletes(workdir):
    """`prune --json --yes` deletes the selected flows and reports them.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["prune", "--older-than", "1", "--json", "--yes"])
    assert result.exit_code == 0, result.output
    assert not f.exists()
    payload = json.loads(result.output)
    assert payload["deleted"] == ["20200101_aaaaaaaa_hello"]


def test_rm_json_without_yes_declined_keeps_dir(workdir):
    """`rm --json` still honors the confirmation gate; declining keeps the dir.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(
        app, ["rm", "20200101_aaaaaaaa_hello", "--json"], input="n\n"
    )
    assert result.exit_code != 0
    assert f.exists()


def test_rm_running_refused_without_force(workdir):
    """`rm` on a running flow is refused (non-zero) and leaves the dir.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello", status="running")
    runner = CliRunner()
    result = runner.invoke(app, ["rm", "20200101_aaaaaaaa_hello", "--yes"])
    assert result.exit_code != 0
    assert "still running" in result.output
    assert f.exists()


def test_rm_running_with_force_deletes(workdir):
    """`rm --force` deletes a running flow.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello", status="running")
    runner = CliRunner()
    result = runner.invoke(
        app, ["rm", "20200101_aaaaaaaa_hello", "--force", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert not f.exists()


def test_rm_declined_confirm_keeps_dir(workdir):
    """Declining the rm confirmation leaves the flow dir intact.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["rm", "20200101_aaaaaaaa_hello"], input="n\n")
    assert result.exit_code != 0
    assert f.exists()


def test_rm_yes_skips_prompt_and_deletes(workdir):
    """`rm --yes` deletes a terminal flow without prompting.

    :param workdir: isolated working directory fixture.
    """
    f = _make_flow(workdir, "20200101_aaaaaaaa_hello")
    runner = CliRunner()
    result = runner.invoke(app, ["rm", "20200101_aaaaaaaa_hello", "--yes"])
    assert result.exit_code == 0, result.output
    assert not f.exists()
