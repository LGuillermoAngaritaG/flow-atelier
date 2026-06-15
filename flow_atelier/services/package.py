"""Package install machinery for ``atelier add`` — source, fetch, manifest.

A package is a git repo (or local dir) with an ``atelier-package.yaml`` at its
root describing the conduits and skills to install. This module resolves a
source string, fetches it into the cache, and parses the manifest (falling back
to directory discovery, with a warning, when the manifest is absent).
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

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


def _discover_skills(repo_dir: Path) -> list[str]:
    """List skill dir names under ``skills/`` that contain a SKILL.md.

    :param repo_dir: package root directory.
    """
    root = repo_dir / "skills"
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )


def read_package(repo_dir: Path) -> PackageManifest:
    """Load the package manifest, or fall back to directory discovery.

    Schedules are never read (D7). When ``atelier-package.yaml`` is absent the
    fallback discovers conduits/skills from the on-disk layout and warns, so a
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
    skills = _discover_skills(repo_dir)
    logger.warning(
        "no atelier-package.yaml in %s; discovered %d conduit(s) and %d skill(s) "
        "by directory scan",
        repo_dir, len(conduits), len(skills),
    )
    return PackageManifest(
        name=repo_dir.name, version=1, conduits=conduits, skills=skills
    )
