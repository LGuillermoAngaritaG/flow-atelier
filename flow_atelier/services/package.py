"""Package install machinery for ``atelier add`` — source, fetch, manifest.

A package is a git repo (or local dir) with an ``atelier-package.yaml`` at its
root describing the conduits to install. This module resolves a source string,
fetches it into the cache, and parses the manifest (falling back to directory
discovery, with a warning, when the manifest is absent).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from flow_atelier.schemas.conduit import Conduit
from flow_atelier.schemas.package import PackageManifest

logger = logging.getLogger(__name__)

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class PackageError(Exception):
    """Raised when a package source can't be resolved, fetched, or parsed."""


@dataclass
class PackageSource:
    """A resolved install source.

    :param raw: the original source string the user passed.
    :param is_git: True for a git URL / shorthand, False for a local path.
    :param location: the git URL or absolute local path to fetch from.
    :param cache_name: directory name to use under the cache root.
    """

    raw: str
    is_git: bool
    location: str
    cache_name: str


def _git_basename(url: str) -> str:
    """Return the repo name from a git URL, stripping a trailing ``.git``.

    :param url: git URL or scp-like address.
    """
    tail = url.rstrip("/").split("/")[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def resolve_source(raw: str) -> PackageSource:
    """Classify an install source as a git URL, ``owner/repo``, or local path.

    :param raw: source string: ``https://….git``, ``git@…``, ``owner/repo``,
        or a local path (absolute or relative).
    :raises PackageError: if the source matches none of the accepted forms.
    """
    s = raw.strip()
    if s.startswith(("https://", "http://", "git@", "ssh://")) or s.endswith(".git"):
        return PackageSource(raw=raw, is_git=True, location=s, cache_name=_git_basename(s))
    path = Path(s).expanduser()
    if path.exists():
        resolved = path.resolve()
        return PackageSource(
            raw=raw, is_git=False, location=str(resolved), cache_name=resolved.name
        )
    if _OWNER_REPO_RE.match(s):
        owner, repo = s.split("/")
        return PackageSource(
            raw=raw,
            is_git=True,
            location=f"https://github.com/{owner}/{repo}.git",
            cache_name=repo,
        )
    raise PackageError(
        f"cannot resolve source: {raw!r} "
        "(expected a git URL, owner/repo, or an existing path)"
    )


def _git_fetch(url: str, dest: Path, ref: str | None) -> None:
    """Clone ``url`` into ``dest`` (or fetch+reset if it already exists).

    :param url: git URL to clone.
    :param dest: target cache directory.
    :param ref: optional branch/tag/commit to check out.
    :raises PackageError: if git is unavailable or the command fails.
    """
    if shutil.which("git") is None:
        raise PackageError("git is required to install from a remote source")
    try:
        if (dest / ".git").exists():
            subprocess.run(
                ["git", "-C", str(dest), "fetch", "--depth", "1", "origin",
                 *( [ref] if ref else [] )],
                check=True, capture_output=True, text=True,
            )
            target = ref or "FETCH_HEAD"
            subprocess.run(
                ["git", "-C", str(dest), "reset", "--hard", target],
                check=True, capture_output=True, text=True,
            )
        else:
            if dest.exists():
                shutil.rmtree(dest)
            cmd = ["git", "clone", "--depth", "1"]
            if ref:
                cmd += ["--branch", ref]
            cmd += [url, str(dest)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise PackageError(f"git failed: {e.stderr.strip() or e}") from e


def fetch_source(
    source: PackageSource, cache_root: Path, ref: str | None = None
) -> Path:
    """Fetch ``source`` into ``cache_root/<cache_name>`` and return that path.

    :param source: a resolved :class:`PackageSource`.
    :param cache_root: directory under which the package cache lives.
    :param ref: optional git ref (ignored for local sources).
    :raises PackageError: on a git failure or a missing local source.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    dest = cache_root / source.cache_name
    if source.is_git:
        _git_fetch(source.location, dest, ref)
    else:
        src_path = Path(source.location)
        if not src_path.exists():
            raise PackageError(f"local source not found: {source.location}")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_path, dest)
    return dest


def _discover_conduits(repo_dir: Path) -> list[str]:
    """List conduit dir names under ``.atelier/conduits/`` with a conduit.yaml.

    :param repo_dir: package root directory.
    """
    root = repo_dir / ".atelier" / "conduits"
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "conduit.yaml").exists()
    )


def read_package(repo_dir: Path) -> PackageManifest:
    """Load the package manifest, or fall back to directory discovery.

    Schedules are never read (D7). When ``atelier-package.yaml`` is absent the
    fallback discovers conduits from the on-disk layout and warns, so a
    partial install doesn't read as success.

    :param repo_dir: package root directory (a fetched cache dir).
    :raises PackageError: if the manifest is present but invalid.
    """
    manifest_path = repo_dir / "atelier-package.yaml"
    if manifest_path.exists():
        try:
            data = yaml.safe_load(manifest_path.read_text()) or {}
            return PackageManifest.model_validate(data)
        except (yaml.YAMLError, ValueError) as e:
            raise PackageError(f"invalid atelier-package.yaml: {e}") from e
    conduits = _discover_conduits(repo_dir)
    logger.warning(
        "no atelier-package.yaml in %s; discovered %d conduit(s) by directory scan",
        repo_dir, len(conduits),
    )
    return PackageManifest(name=repo_dir.name, version=1, conduits=conduits)


@dataclass
class InstallReport:
    """What an install actually wrote vs. skipped.

    ``conduits_installed`` are package-owned (safe for ``remove`` to delete);
    ``conduits_skipped`` pre-existed and were left untouched (not owned).
    """

    name: str
    scope: str
    conduit_root: Path
    conduits_installed: list[str] = field(default_factory=list)
    conduits_skipped: list[str] = field(default_factory=list)


def install_package(
    repo_dir: Path,
    manifest: PackageManifest,
    *,
    conduit_root: Path,
    scope: str,
    force: bool = False,
) -> InstallReport:
    """Copy declared conduits into their install target.

    Copies each conduit's *whole directory* (so picker.py / templates travel),
    after confirming its ``conduit.yaml`` parses. On collision (target exists),
    skip-and-warn unless ``force``; skipped items are not recorded as owned.

    :param repo_dir: the fetched package directory.
    :param manifest: the parsed package manifest.
    :param conduit_root: the ``conduits/`` dir to install conduits into.
    :param scope: ``"global"`` or ``"project"`` (recorded in the report).
    :param force: overwrite colliding conduits instead of skipping.
    :raises PackageError: a declared conduit is missing or invalid.
    """
    report = InstallReport(
        name=manifest.name, scope=scope, conduit_root=conduit_root,
    )
    src_conduits = repo_dir / ".atelier" / "conduits"
    for name in manifest.conduits:
        src = src_conduits / name
        yaml_path = src / "conduit.yaml"
        if not yaml_path.exists():
            raise PackageError(f"declared conduit not found in package: {name}")
        try:
            Conduit.model_validate(yaml.safe_load(yaml_path.read_text()))
        except (yaml.YAMLError, ValueError) as e:
            raise PackageError(f"conduit {name!r} has an invalid conduit.yaml: {e}") from e
        dest = conduit_root / name
        if dest.exists() and not force:
            logger.warning("conduit %s already exists, skipping (use --force)", name)
            report.conduits_skipped.append(name)
            continue
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        report.conduits_installed.append(name)
    return report


@dataclass
class RemoveReport:
    """What an uninstall actually deleted."""

    name: str
    conduits_removed: list[str] = field(default_factory=list)


def read_lockfile(path: Path) -> dict:
    """Return the parsed install lockfile, or an empty dict if absent.

    :param path: path to ``installed.json``.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_lockfile(path: Path, name: str, entry: dict) -> None:
    """Record (or replace) ``name``'s entry in the lockfile at ``path``.

    :param path: path to ``installed.json``.
    :param name: package name (lockfile key).
    :param entry: the package's recorded install metadata.
    """
    data = read_lockfile(path)
    data[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def delete_lockfile_entry(path: Path, name: str) -> dict | None:
    """Remove and return ``name``'s lockfile entry, or None if absent.

    :param path: path to ``installed.json``.
    :param name: package name (lockfile key).
    """
    data = read_lockfile(path)
    entry = data.pop(name, None)
    if entry is not None:
        path.write_text(json.dumps(data, indent=2))
    return entry
