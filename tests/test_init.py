"""Tests for `atelier init`."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from app.main import app
from app.schemas.conduit import Conduit


@pytest.fixture
def fresh_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_creates_hello_conduit(fresh_cwd):
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
    runner = CliRunner()
    runner.invoke(app, ["init"])
    assert not (fresh_cwd / ".atelier" / "flows").exists()


def test_init_is_idempotent_when_atelier_exists(fresh_cwd):
    (fresh_cwd / ".atelier").mkdir()
    (fresh_cwd / ".atelier" / "marker").write_text("keep me")
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "already set up" in result.output.lower()
    # nothing was touched
    assert (fresh_cwd / ".atelier" / "marker").read_text() == "keep me"
    assert not (fresh_cwd / ".atelier" / "conduits").exists()


def test_init_does_not_touch_global(fresh_cwd, _isolate_global_atelier_dir):
    runner = CliRunner()
    runner.invoke(app, ["init"])
    global_dir: Path = _isolate_global_atelier_dir
    assert not (global_dir / "conduits" / "hello").exists()


def test_hello_conduit_runs_end_to_end(fresh_cwd):
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0
    run_result = runner.invoke(app, ["run", "hello", "--input", "name=world"])
    assert run_result.exit_code == 0, run_result.output
    assert "flow_id" in run_result.output
