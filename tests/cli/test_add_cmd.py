"""CLI tests for `atelier add` — install a package from a local path."""
from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from flow_atelier.cli import app

CONDUIT_YAML = """
name: demo
description: demo
tasks:
  - go:
      description: go
      task: "echo hi"
      tool: tool:bash
      depends_on: []
"""

MANIFEST_YAML = """
name: demo-pkg
version: 1
conduits:
  - demo
skills:
  - idea
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated HOME + atelier dirs and a local package source.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    home = tmp_path / "home"
    home.mkdir()
    global_dir = tmp_path / "global"
    (global_dir / "conduits").mkdir(parents=True)
    proj = tmp_path / "proj"
    (proj / ".atelier" / "conduits").mkdir(parents=True)
    monkeypatch.chdir(proj)
    for k in list(os.environ):
        if k.startswith("ATELIER_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(global_dir))
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")

    pkg = tmp_path / "pkgsrc"
    conduit = pkg / ".atelier" / "conduits" / "demo"
    conduit.mkdir(parents=True)
    (conduit / "conduit.yaml").write_text(CONDUIT_YAML)
    skill = pkg / "skills" / "idea"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# idea\n")
    (pkg / "atelier-package.yaml").write_text(MANIFEST_YAML)

    return {"home": home, "global": global_dir, "pkg": pkg}


def test_add_installs_conduit_skills_and_lockfile(env):
    """`add <local>` populates conduit + both skill dirs + installed.json."""
    result = CliRunner().invoke(app, ["add", str(env["pkg"])])
    assert result.exit_code == 0, result.output
    assert (env["global"] / "conduits" / "demo" / "conduit.yaml").exists()
    assert (env["home"] / ".claude" / "skills" / "idea" / "SKILL.md").exists()
    assert (env["home"] / ".agents" / "skills" / "idea" / "SKILL.md").exists()
    lock = json.loads((env["global"] / "installed.json").read_text())
    assert lock["demo-pkg"]["conduits"] == ["demo"]
    assert lock["demo-pkg"]["skills"] == ["idea"]
    assert "atelier run demo" in result.output


def test_add_collision_skips_without_force_exit_zero(env):
    """A second `add` skips the existing skill, warns, and exits 0."""
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    result = CliRunner().invoke(app, ["add", str(env["pkg"])])
    assert result.exit_code == 0, result.output
    assert "~" in result.output  # skipped marker
    assert "skipped" in result.output


def test_add_force_overwrites(env):
    """`add --force` overwrites an existing skill."""
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    user_skill = env["home"] / ".claude" / "skills" / "idea" / "SKILL.md"
    user_skill.write_text("# changed\n")
    result = CliRunner().invoke(app, ["add", str(env["pkg"]), "--force"])
    assert result.exit_code == 0, result.output
    assert user_skill.read_text() == "# idea\n"


def test_remove_deletes_recorded_dirs(env):
    """`remove` deletes exactly the recorded conduit and skill dirs."""
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    result = CliRunner().invoke(app, ["remove", "demo-pkg"])
    assert result.exit_code == 0, result.output
    assert not (env["global"] / "conduits" / "demo").exists()
    assert not (env["home"] / ".claude" / "skills" / "idea").exists()
    assert not (env["home"] / ".agents" / "skills" / "idea").exists()
    assert json.loads((env["global"] / "installed.json").read_text()) == {}


def test_remove_preserves_collision_skipped_skill(env):
    """A skill skipped on collision is the user's, so `remove` leaves it."""
    user_skill = env["home"] / ".claude" / "skills" / "idea"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("# user's own\n")
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    assert CliRunner().invoke(app, ["remove", "demo-pkg"]).exit_code == 0
    assert (user_skill / "SKILL.md").read_text() == "# user's own\n"


def test_remove_unknown_package_errors(env):
    """Removing an unknown package exits 1 with a clear message."""
    result = CliRunner().invoke(app, ["remove", "nope"])
    assert result.exit_code == 1
    assert "not installed" in result.output
    assert "Traceback" not in result.output


def test_update_force_propagates_source_change(env):
    """`update --force` re-installs and propagates a changed source file."""
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    # modify the source conduit
    (env["pkg"] / ".atelier" / "conduits" / "demo" / "conduit.yaml").write_text(
        CONDUIT_YAML.replace("echo hi", "echo CHANGED")
    )
    result = CliRunner().invoke(app, ["update", "demo-pkg", "--force"])
    assert result.exit_code == 0, result.output
    installed = (
        env["global"] / "conduits" / "demo" / "conduit.yaml"
    ).read_text()
    assert "echo CHANGED" in installed


def test_update_without_force_preserves_lockfile_ownership(env):
    """`update` without --force keeps conduits/skills owned in the lockfile."""
    assert CliRunner().invoke(app, ["add", str(env["pkg"])]).exit_code == 0
    assert CliRunner().invoke(app, ["update", "demo-pkg"]).exit_code == 0
    lock = json.loads((env["global"] / "installed.json").read_text())
    assert lock["demo-pkg"]["conduits"] == ["demo"]
    assert lock["demo-pkg"]["skills"] == ["idea"]


def test_update_unknown_package_errors(env):
    """Updating an unknown package exits 1 referencing `atelier add`."""
    result = CliRunner().invoke(app, ["update", "nope"])
    assert result.exit_code == 1
    assert "not installed" in result.output
    assert "atelier add" in result.output
