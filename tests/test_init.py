"""Tests for `atelier init`."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from flow_atelier.cli import app
from flow_atelier.schemas.conduit import Conduit


@pytest.fixture
def fresh_cwd(tmp_path, monkeypatch):
    """Provide a fresh working directory for `atelier init` tests.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_creates_hello_conduit(fresh_cwd):
    """Verify `atelier init` creates the hello conduit on disk.

    :param fresh_cwd: fresh working directory fixture.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output

    conduit_path = fresh_cwd / ".atelier" / "conduits" / "hello" / "conduit.yaml"
    assert conduit_path.exists()

    data = yaml.safe_load(conduit_path.read_text())
    conduit = Conduit.model_validate(data)
    assert conduit.name == "hello"
    assert len(conduit.tasks) == 1
    assert conduit.tasks[0].tool.value == "tool:bash"


def test_init_does_not_create_flows(fresh_cwd):
    """Verify `atelier init` does not create a flows directory.

    :param fresh_cwd: fresh working directory fixture.
    """
    runner = CliRunner()
    runner.invoke(app, ["init"])
    assert not (fresh_cwd / ".atelier" / "flows").exists()


def test_init_is_idempotent_when_atelier_exists(fresh_cwd):
    """Verify `atelier init` fills in the hello conduit when `.atelier` exists
    for another reason, then is a no-op once the conduit is present.

    :param fresh_cwd: fresh working directory fixture.
    """
    (fresh_cwd / ".atelier").mkdir()
    (fresh_cwd / ".atelier" / "marker").write_text("keep me")
    runner = CliRunner()
    conduit_path = fresh_cwd / ".atelier" / "conduits" / "hello" / "conduit.yaml"

    # First run: .atelier exists but the hello conduit doesn't — scaffold it,
    # preserving unrelated content rather than bailing out.
    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    assert conduit_path.exists()
    assert (fresh_cwd / ".atelier" / "marker").read_text() == "keep me"

    # Second run: the conduit now exists — a genuine no-op.
    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0
    assert "already set up" in second.output.lower()


def test_init_does_not_touch_global(fresh_cwd, _isolate_global_atelier_dir):
    """Verify `atelier init` does not write into the global atelier dir.

    :param fresh_cwd: fresh working directory fixture.
    :param _isolate_global_atelier_dir: isolated global atelier dir fixture.
    """
    runner = CliRunner()
    runner.invoke(app, ["init"])
    global_dir: Path = _isolate_global_atelier_dir
    assert not (global_dir / "conduits" / "hello").exists()


def test_hello_conduit_runs_end_to_end(fresh_cwd):
    """Verify the scaffolded hello conduit runs end-to-end.

    :param fresh_cwd: fresh working directory fixture.
    """
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0
    run_result = runner.invoke(app, ["run", "hello", "--input", "name=world"])
    assert run_result.exit_code == 0, run_result.output
    assert "flow_id" in run_result.output
