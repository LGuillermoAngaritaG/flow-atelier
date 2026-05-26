"""Pick the next autonomous project to work on, or emit a SKIP reason.

Stdout contract (single line, always exit 0):
    READY: <absolute path to chosen .md file>
    SKIP:  <human-readable reason>

Filters, in order:
    1. Claude Code 5h-window usage gate (read from ~/.claude/rate-limit-cache.json
       written by the statusline hook).
    2. Pending-Review section item count
    3. Idle time = max(latest git commit, latest mtime under `location`)
    4. Sort survivors by frontmatter priority asc; on ties, the project
       markdown file with the oldest mtime wins (= task list untouched longest).
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
    """Parse the simple key: value frontmatter block at the top of a project file.

    Returns None if no frontmatter is present.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_SECTION_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def count_section_items(text: str, section_name: str) -> int:
    """Count top-level `* ` bullets under a `# <section_name>` heading."""
    # find the section heading line
    pattern = re.compile(
        rf"^#\s+{re.escape(section_name)}\s*$(.*?)(?=^#\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return 0
    body = m.group(1)
    return sum(1 for line in body.splitlines() if line.lstrip().startswith("* "))


# ---------- usage gate ----------


def claude_usage_pct(token_limit: int) -> tuple[float | None, str | None]:
    """Return (pct_used, error). pct_used is None when the cache is unreadable.

    Reads the 5h rate-limit snapshot that the statusline hook writes to
    ``~/.claude/rate-limit-cache.json`` on every Claude Code refresh. The
    ``token_limit`` argument is accepted for backwards-compatible CLI plumbing
    but ignored — the cached value is already a server-side percentage.
    """
    del token_limit  # no longer used; kept for CLI compatibility
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
        return 0.0, None  # 5h window has rolled over since the snapshot
    return float(pct), None


# ---------- idle gate ----------

_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache",
                ".pytest_cache", "dist", "build", ".next"}


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


def git_last_commit_ts(path: Path) -> float:
    """Return Unix ts of last commit in `path`. 0 if not a repo or no commits."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=10,
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
    parser.add_argument("--projects-dir", required=True)
    parser.add_argument("--max-usage-pct", type=float, required=True)
    parser.add_argument("--idle-hours", type=float, required=True)
    parser.add_argument("--max-pending-review", type=int, required=True)
    parser.add_argument("--token-limit", type=int, required=True,
                        help="Token ceiling used to compute usage %. e.g. 19000000.")
    args = parser.parse_args()

    pct, err = claude_usage_pct(args.token_limit)
    if pct is None:
        print(f"SKIP: cannot determine Claude usage ({err})")
        return 0
    if pct >= args.max_usage_pct:
        print(f"SKIP: Claude Code usage {pct:.1f}% >= threshold {args.max_usage_pct:.0f}%")
        return 0

    projects_dir = Path(args.projects_dir).expanduser()
    if not projects_dir.is_dir():
        print(f"SKIP: projects_dir does not exist: {projects_dir}")
        return 0

    files = sorted(projects_dir.glob("*.md"))
    if not files:
        print(f"SKIP: no .md files in {projects_dir}")
        return 0

    total = len(files)
    parsed: list[tuple[Path, dict[str, str], str]] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            print(f"warn: skipping {f.name}: no frontmatter", file=sys.stderr)
            continue
        parsed.append((f, fm, text))

    # Pending-Review gate
    survivors_pr: list[tuple[Path, dict[str, str], str]] = []
    pr_filtered = 0
    for f, fm, text in parsed:
        if count_section_items(text, "Pending-Review") >= args.max_pending_review:
            pr_filtered += 1
            continue
        survivors_pr.append((f, fm, text))

    # Idle gate
    now = time.time()
    idle_cutoff_secs = args.idle_hours * 3600.0
    survivors_idle: list[tuple[Path, dict[str, str], float]] = []
    idle_filtered = 0
    for f, fm, _text in survivors_pr:
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
            f"({idle_filtered} filtered by idle, {pr_filtered} by pending-review, "
            f"{total} total)"
        )
        return 0

    # Sort: priority asc (1 = highest); tie-break on oldest project-file
    # mtime so projects whose task list has been edited least recently win.
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
    winner = survivors_idle[0][0]
    print(f"READY: {winner}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
