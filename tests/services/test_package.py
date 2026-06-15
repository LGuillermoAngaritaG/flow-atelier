"""Package service tests (source resolution, fetch, manifest parse)."""
import pytest

from flow_atelier.schemas.package import PackageManifest
from flow_atelier.services.package import (
    PackageError,
    fetch_source,
    install_package,
    read_lockfile,
    read_package,
    resolve_source,
    write_lockfile,
)

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


def _make_repo(root, *, manifest=True):
    """Build a package repo fixture under ``root``.

    :param root: directory to populate.
    :param manifest: when True, write atelier-package.yaml.
    """
    conduit = root / ".atelier" / "conduits" / "demo"
    conduit.mkdir(parents=True)
    (conduit / "conduit.yaml").write_text(CONDUIT_YAML)
    (conduit / "picker.py").write_text("print('pick')\n")
    skill = root / "skills" / "idea"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# idea\n")
    if manifest:
        (root / "atelier-package.yaml").write_text(MANIFEST_YAML)
    return root


def _manifest():
    """Return the demo manifest (one conduit, one skill)."""
    return PackageManifest(name="demo-pkg", conduits=["demo"], skills=["idea"])


def test_resolve_owner_repo_to_github_url():
    """owner/repo shorthand resolves to the GitHub HTTPS URL."""
    src = resolve_source("goldenguille/autonomous-projects")
    assert src.is_git is True
    assert src.location == (
        "https://github.com/goldenguille/autonomous-projects.git"
    )
    assert src.cache_name == "autonomous-projects"


def test_resolve_git_url_keeps_url_and_derives_cache_name():
    """A full .git URL is kept as-is with cache name from its basename."""
    src = resolve_source("https://github.com/owner/repo.git")
    assert src.is_git is True
    assert src.location == "https://github.com/owner/repo.git"
    assert src.cache_name == "repo"


def test_resolve_local_path(tmp_path):
    """An existing local path resolves to a non-git absolute source."""
    repo = _make_repo(tmp_path / "pkgsrc")
    src = resolve_source(str(repo))
    assert src.is_git is False
    assert src.location == str(repo.resolve())
    assert src.cache_name == "pkgsrc"


def test_resolve_unknown_source_raises():
    """A source that is neither URL, owner/repo, nor path raises."""
    with pytest.raises(PackageError):
        resolve_source("not a valid source!!")


def test_fetch_local_copytrees_into_cache(tmp_path):
    """A local source is copytree'd into the cache under its cache name."""
    repo = _make_repo(tmp_path / "pkgsrc")
    cache = tmp_path / "cache"
    src = resolve_source(str(repo))
    dest = fetch_source(src, cache)
    assert dest == cache / "pkgsrc"
    assert (dest / "atelier-package.yaml").exists()
    assert (dest / ".atelier" / "conduits" / "demo" / "conduit.yaml").exists()


def test_fetch_local_overwrites_existing_cache(tmp_path):
    """Re-fetching a local source replaces a stale cache directory."""
    repo = _make_repo(tmp_path / "pkgsrc")
    cache = tmp_path / "cache"
    src = resolve_source(str(repo))
    fetch_source(src, cache)
    (repo / "NEW.txt").write_text("new")
    dest = fetch_source(src, cache)
    assert (dest / "NEW.txt").exists()


def test_fetch_git_without_git_on_path_raises(tmp_path, monkeypatch):
    """A git source errors clearly when git is not on PATH."""
    monkeypatch.setattr("flow_atelier.services.package.shutil.which", lambda _: None)
    src = resolve_source("owner/repo")
    with pytest.raises(PackageError, match="git is required"):
        fetch_source(src, tmp_path / "cache")


def test_read_package_declared_manifest(tmp_path):
    """read_package returns the declared conduits/skills from the manifest."""
    repo = _make_repo(tmp_path / "pkgsrc")
    manifest = read_package(repo)
    assert isinstance(manifest, PackageManifest)
    assert manifest.name == "demo-pkg"
    assert manifest.conduits == ["demo"]
    assert manifest.skills == ["idea"]


def test_read_package_fallback_discovers_and_warns(tmp_path, caplog):
    """Without a manifest, read_package discovers conduits/skills and warns."""
    repo = _make_repo(tmp_path / "pkgsrc", manifest=False)
    with caplog.at_level("WARNING"):
        manifest = read_package(repo)
    assert manifest.conduits == ["demo"]
    assert manifest.skills == ["idea"]
    assert any("atelier-package.yaml" in r.message for r in caplog.records)


# ------------------------------------------------------------------ install


def test_install_copies_whole_conduit_dir_and_skills(tmp_path):
    """install_package copies the whole conduit dir and skills into all roots."""
    repo = _make_repo(tmp_path / "pkgsrc")
    conduit_root = tmp_path / "global" / "conduits"
    roots = [tmp_path / "claude" / "skills", tmp_path / "agents" / "skills"]
    report = install_package(
        repo, _manifest(), conduit_root=conduit_root,
        skill_roots=roots, scope="global",
    )
    assert report.conduits_installed == ["demo"]
    assert report.skills_installed == ["idea"]
    assert (conduit_root / "demo" / "conduit.yaml").exists()
    assert (conduit_root / "demo" / "picker.py").exists()
    for root in roots:
        assert (root / "idea" / "SKILL.md").exists()


def test_install_skips_existing_skill_and_does_not_own_it(tmp_path):
    """A pre-existing skill in any root is skipped and not recorded as owned."""
    repo = _make_repo(tmp_path / "pkgsrc")
    conduit_root = tmp_path / "global" / "conduits"
    roots = [tmp_path / "claude" / "skills", tmp_path / "agents" / "skills"]
    (roots[0] / "idea").mkdir(parents=True)
    (roots[0] / "idea" / "SKILL.md").write_text("# user's own\n")
    report = install_package(
        repo, _manifest(), conduit_root=conduit_root,
        skill_roots=roots, scope="global",
    )
    assert report.skills_skipped == ["idea"]
    assert report.skills_installed == []
    assert (roots[0] / "idea" / "SKILL.md").read_text() == "# user's own\n"


def test_install_force_overwrites_existing_skill(tmp_path):
    """--force overwrites a colliding skill and records it as owned."""
    repo = _make_repo(tmp_path / "pkgsrc")
    conduit_root = tmp_path / "global" / "conduits"
    roots = [tmp_path / "claude" / "skills", tmp_path / "agents" / "skills"]
    (roots[0] / "idea").mkdir(parents=True)
    (roots[0] / "idea" / "SKILL.md").write_text("# user's own\n")
    report = install_package(
        repo, _manifest(), conduit_root=conduit_root,
        skill_roots=roots, scope="global", force=True,
    )
    assert report.skills_installed == ["idea"]
    assert (roots[0] / "idea" / "SKILL.md").read_text() == "# idea\n"


def test_install_invalid_conduit_yaml_raises(tmp_path):
    """A conduit whose conduit.yaml fails validation is reported, not skipped."""
    repo = _make_repo(tmp_path / "pkgsrc")
    (repo / ".atelier" / "conduits" / "demo" / "conduit.yaml").write_text(
        "name: demo\n"  # missing required fields
    )
    with pytest.raises(PackageError, match="invalid conduit.yaml"):
        install_package(
            repo, _manifest(), conduit_root=tmp_path / "g" / "conduits",
            skill_roots=[tmp_path / "s"], scope="global",
        )


def test_lockfile_roundtrips(tmp_path):
    """write_lockfile then read_lockfile returns the recorded entry."""
    path = tmp_path / "installed.json"
    write_lockfile(path, "demo-pkg", {"source": "x", "conduits": ["demo"]})
    write_lockfile(path, "other", {"source": "y"})
    data = read_lockfile(path)
    assert data["demo-pkg"]["conduits"] == ["demo"]
    assert data["other"]["source"] == "y"
