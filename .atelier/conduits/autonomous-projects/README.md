# autonomous-projects

A conduit that picks one project from a directory of Obsidian-style project
markdown files and hands it to Claude Code to advance.

## Project file format

Each `*.md` file under `projects_dir` is one project:

```markdown
---
description: Short description
goal: What you want done
priority: 1            # integer; lower = higher priority
location: /abs/path/to/project/working/dir
use_git: true          # or false
---
# To-Do's
* **task_name** task description

# In-Progress
* **task_name** task description

# Pending-Review
* **task_name:** description
    * **summary:** what was done
    * **location:** local path or PR URL

# Done
* **task_name:** description
    * **summary:** what was done
    * **location:** local path or PR URL
```

## How the pick works

`picker.py` runs four gates in order:

1. **Claude usage gate.** Calls `npx ccusage blocks --active --json`, divides
   `totalTokens` by `token_limit`, and skips if the result is `>= max_usage_pct`.
2. **Frontmatter parse.** Files without `---`-delimited frontmatter are
   warned to stderr and dropped.
3. **Pending-Review gate.** Projects with `max_pending_review` or more
   bullets under `# Pending-Review` are dropped. The worker only ever moves
   completed tasks to `# Pending-Review`; only the human reviewer moves
   them to `# Done`. This caps how much un-reviewed work piles up before
   the picker skips the project.
4. **Idle gate.** For each survivor, `last_touched = max(git_last_commit,
   max_mtime_under(location))`. Projects touched in the last `idle_hours`
   are dropped. (`use_git: true` enables the git half; otherwise only mtime
   is considered.)

Survivors are sorted by `priority` ascending; the stalest one wins on ties.

Stdout is always one line:
- `READY: /abs/path/to/winner.md` — the worker task runs.
- `SKIP: <reason>` — the worker task is auto-skipped by the engine.

## Files

- `conduit.yaml` — two-task DAG: `pick_project` (bash) → `work_on_project` (claude-code).
- `picker.py` — stdlib-only Python picker.
- `schedule.example.yaml` — example schedule you can install.

## Manual run

```bash
atelier run autonomous-projects \
  --input projects_dir="/Users/ganga/Library/Mobile Documents/iCloud~md~obsidian/Documents/Cerebro/AUTONOMOUS_PROJECTS/WORKING" \
  --input max_usage_pct=80 \
  --input idle_hours=2 \
  --input max_pending_review=3 \
  --input token_limit=19000000
```

All five inputs are required at run time (no per-conduit defaults exist in
the framework). Edit `schedule.example.yaml` for your preferred values.

## Schedule

```bash
atelier schedule add .atelier/conduits/autonomous-projects/schedule.example.yaml
atelier scheduler start    # foreground daemon; Ctrl+C to stop
```

`atelier schedule list` shows the next fire times. Use `atelier schedule
run-now autonomous-projects-tick` to fire it once on demand.

## Machine-specific bits

- `conduit.yaml` references `picker.py` by absolute path. If you move this
  repo, update the `python3 ...picker.py` line in `conduit.yaml`.
- The example projects_dir points at an iCloud-synced Obsidian vault on
  this machine. Change it in `schedule.example.yaml` if needed.
- `token_limit` is a coarse approximation of your Claude Code 5h quota.
  Tune it based on what `npx ccusage blocks` shows during a typical session.
