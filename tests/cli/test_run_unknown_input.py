"""CLI test: `atelier run` rejects undeclared --input keys before starting."""
from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from flow_atelier.cli import app


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolated cwd with an empty `.atelier` tree and isolated global dir.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    (tmp_path / ".atelier" / "conduits").mkdir(parents=True)
    global_dir = tmp_path / "global"
    (global_dir / "conduits").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(global_dir))
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")
    return tmp_path


def _write_conduit(workdir, name: str, body: str) -> None:
    """Write a conduit.yaml under the isolated `.atelier` tree.

    :param workdir: the isolated working directory fixture.
    :param name: conduit name (also the directory name).
    :param body: full YAML contents to write.
    """
    cdir = workdir / ".atelier" / "conduits" / name
    cdir.mkdir(parents=True)
    (cdir / "conduit.yaml").write_text(body)


def test_rejects_undeclared_key_with_suggestion(workdir):
    """A near-miss key exits 1, names the typo, and suggests the real key."""
    _write_conduit(
        workdir,
        "echo",
        "name: echo\ndescription: d\n"
        "inputs:\n  project:\n    description: the project\n"
        "tasks:\n  - name: t\n    description: b\n    task: echo hi\n    tool: tool:bash\n",
    )
    result = CliRunner().invoke(app, ["run", "echo", "--input", "prj=foo"])
    assert result.exit_code == 1
    assert "unknown input" in result.stdout
    assert "did you mean" in result.stdout
    assert "project" in result.stdout
    assert "starting flow" not in result.stdout


def test_rejects_undeclared_key_without_suggestion(workdir):
    """A key unlike any declared one exits 1 with no suggestion."""
    _write_conduit(
        workdir,
        "echo",
        "name: echo\ndescription: d\n"
        "inputs:\n  project:\n    description: the project\n"
        "tasks:\n  - name: t\n    description: b\n    task: echo hi\n    tool: tool:bash\n",
    )
    result = CliRunner().invoke(
        app, ["run", "echo", "--input", "totallyunrelated=foo"]
    )
    assert result.exit_code == 1
    assert "unknown input" in result.stdout
    assert "did you mean" not in result.stdout


def test_declared_key_passes_unknown_guard(workdir):
    """A correctly declared key is not flagged by the unknown-input guard."""
    _write_conduit(
        workdir,
        "echo",
        "name: echo\ndescription: d\n"
        "inputs:\n  project:\n    description: the project\n    default: x\n"
        "tasks:\n  - name: t\n    description: b\n    task: echo hi\n    tool: tool:bash\n",
    )
    result = CliRunner().invoke(app, ["run", "echo", "--input", "project=foo"])
    assert "unknown input" not in result.stdout
