"""Pick the next autonomous project to work on, or emit a SKIP reason.

Stdout contract (always exit 0):
    READY: <absolute path to chosen project .md file>
    NAME: <project file stem>
    LOCATION: <frontmatter location (codebase dir)>
    MAX_IDEAS: <frontmatter max_ideas, default 20>
    MAX_PENDING_REVIEW: <frontmatter max_pending_review, default 5>
  or
    SKIP:  <human-readable reason>

Filters, in order:
    1. Claude Code 5h-window usage gate
    2. PAUSED gate (skip if project name exists in projects/paused/)
    3. In-progress gate (resume project with a task in in-progress/)
    4. Idle time = max(latest git commit, latest mtime under `location`)
    5. Sort survivors by frontmatter priority asc; ties broken by oldest
       project file mtime.

The pending-review cap is NOT enforced here — it only throttles to-do
execution, which the conduit gates separately. A project with a full
pending-review/ stays eligible so idea/review generation keeps running.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ---------- frontmatter parsing ----------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str] | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ---------- usage gate ----------


def claude_usage_pct(token_limit: int) -> tuple[float | None, str | None]:
    """Return (pct_used, error). pct_used is None when the cache is unreadable."""
    del token_limit  # accepted for CLI compatibility, unused
    cache_path = Path.home() / ".claude" / "rate-limit-cache.json"
    try:
        payload = json.loads(cache_path.read_text())
    except FileNotFoundError:
        return None, f"rate-limit cache missing: {cache_path}"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"rate-limit cache unreadable: {exc}"
    five_hour = payload.get("five_hour") or {}
    pct = five_hour.get("used_percentage")
    resets_at = five_hour.get("resets_at")
    if pct is None or resets_at is None:
        return None, "rate-limit cache missing five_hour fields"
    if resets_at <= time.time():
        return 0.0, None
    return float(pct), None


# ---------- idle gate ----------

_IGNORE_DIRS = {".git", ".atelier", "node_modules", "__pycache__", ".venv",
                ".mypy_cache", ".pytest_cache", "dist", "build", ".next"}


def max_mtime_under(path: Path) -> float:
    """Return the newest mtime of any file under `path`. 0 if empty/missing."""
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    newest = 0.0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            try:
                m = (Path(root) / fname).stat().st_mtime
                if m > newest:
                    newest = m
            except OSError:
                continue
    return newest


def _int_field(fm: dict[str, str], key: str, default: int) -> int:
    """Return the frontmatter int at `key`, or `default` if missing/non-numeric."""
    try:
        return int(str(fm.get(key, "")).strip())
    except (ValueError, TypeError):
        return default


def emit_ready(path: Path, fm: dict[str, str]) -> None:
    print(f"READY: {path}")
    print(f"NAME: {path.stem}")
    print(f"LOCATION: {fm.get('location', '')}")
    print(f"MAX_IDEAS: {_int_field(fm, 'max_ideas', 20)}")
    print(f"MAX_PENDING_REVIEW: {_int_field(fm, 'max_pending_review', 5)}")


def git_last_commit_ts(path: Path) -> float:
    """Return Unix ts of last commit in `path`. 0 if not a repo or no commits."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0.0
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects-dir",
                        default=str(Path(__file__).resolve().parent),
                        help="Conduit root holding projects/ and tasks/. "
                             "Defaults to this script's directory.")
    parser.add_argument("--max-usage-pct", type=float, required=True,
                        help="Skip if Claude usage >= this percent.")
    parser.add_argument("--idle-hours", type=float, required=True,
                        help="Project must be untouched for this many hours.")
    parser.add_argument("--token-limit", type=int, required=True,
                        help="Token ceiling for usage computation.")
    args = parser.parse_args()

    # 1. Usage gate
    pct, err = claude_usage_pct(args.token_limit)
    if pct is None:
        print(f"SKIP: cannot determine Claude usage ({err})")
        return 0
    if pct >= args.max_usage_pct:
        print(f"SKIP: Claude Code usage {pct:.1f}% >= threshold {args.max_usage_pct:.0f}%")
        return 0

    root = Path(args.projects_dir).expanduser()
    if not root.is_dir():
        print(f"SKIP: projects_dir does not exist: {root}")
        return 0

    projects_dir = root / "projects" / "working"
    paused_dir = root / "projects" / "paused"
    tasks_dir = root / "tasks"

    if not projects_dir.is_dir():
        print(f"SKIP: projects/working/ not found under {root}")
        return 0

    files = sorted(projects_dir.glob("*.md"))
    if not files:
        print(f"SKIP: no .md files in {projects_dir}")
        return 0

    # 2. PAUSED gate
    paused_names: set[str] = set()
    if paused_dir.is_dir():
        paused_names = {f.stem for f in paused_dir.glob("*.md")}

    # 3. Parse frontmatter + ensure task folders exist
    _KANBAN = ("to-do", "in-progress", "pending-review", "done")
    _EXTRA_DIRS = ("ideas", "bad_ideas")
    total = len(files)
    parsed: list[tuple[Path, dict[str, str]]] = []
    for f in files:
        if f.stem in paused_names:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            print(f"warn: skipping {f.name}: no frontmatter", file=sys.stderr)
            continue
        project_tasks = tasks_dir / f.stem
        for sub in (*_KANBAN, *_EXTRA_DIRS):
            (project_tasks / sub).mkdir(parents=True, exist_ok=True)
        parsed.append((f, fm))

    # 4. In-progress gate — pick the project with an unfinished task
    for f, fm in parsed:
        ip_dir = tasks_dir / f.stem / "in-progress"
        if ip_dir.is_dir() and any(ip_dir.glob("*.md")):
            emit_ready(f, fm)
            return 0

    # 5. Idle gate
    now = time.time()
    idle_cutoff_secs = args.idle_hours * 3600.0
    survivors_idle: list[tuple[Path, dict[str, str], float]] = []
    idle_filtered = 0
    for f, fm in parsed:
        location = Path(fm.get("location", "")).expanduser()
        mtime = max_mtime_under(location)
        gtime = git_last_commit_ts(location) if fm.get("use_git", "").lower() == "true" else 0.0
        last_touched = max(mtime, gtime)
        if (now - last_touched) < idle_cutoff_secs:
            idle_filtered += 1
            continue
        survivors_idle.append((f, fm, last_touched))

    if not survivors_idle:
        print(
            f"SKIP: no eligible project "
            f"({idle_filtered} idle, {total} total)"
        )
        return 0

    # Sort: priority asc (1 = highest); tie-break on oldest project-file mtime
    def sort_key(entry: tuple[Path, dict[str, str], float]) -> tuple[int, float]:
        f, fm, _lt = entry
        try:
            prio = int(fm.get("priority", "999"))
        except ValueError:
            prio = 999
        try:
            proj_mtime = f.stat().st_mtime
        except OSError:
            proj_mtime = 0.0
        return prio, proj_mtime

    survivors_idle.sort(key=sort_key)
    winner, winner_fm, _lt = survivors_idle[0]
    emit_ready(winner, winner_fm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
