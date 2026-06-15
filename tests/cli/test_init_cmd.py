"""CLI tests for `atelier init` idempotency."""
from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from flow_atelier.cli import app


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolated cwd with no `.atelier` tree and update checks disabled.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")
    return tmp_path


def _conduit_file(workdir):
    """Return the hello conduit path under ``workdir``."""
    return workdir / ".atelier" / "conduits" / "hello" / "conduit.yaml"


def test_init_scaffolds_in_empty_dir(workdir):
    """init creates the hello conduit when nothing exists yet."""
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0
    assert _conduit_file(workdir).exists()


def test_init_fills_in_when_atelier_exists_without_hello(workdir):
    """A pre-existing .atelier/ (without the hello conduit) is filled in."""
    (workdir / ".atelier" / "conduits").mkdir(parents=True)
    assert not _conduit_file(workdir).exists()
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0
    assert _conduit_file(workdir).exists()


def test_init_is_noop_when_hello_conduit_present(workdir):
    """Running init when the hello conduit already exists is a no-op."""
    CliRunner().invoke(app, ["init"])
    original = _conduit_file(workdir).read_text()
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0
    assert "already set up" in result.stdout
    assert _conduit_file(workdir).read_text() == original
