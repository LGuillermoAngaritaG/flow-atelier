# autonomous-projects

A conduit that picks one project from a folder-structured project directory
and advances it via Claude Code.

## Directory structure

```
AUTONOMOUS_PROJECTS/
├── PAUSED/                          # Drop a project .md here to skip it
├── PROJECTS/                        # One .md file per project
│   └── my-project.md
├── TASKS/                           # Kanban folders per project
│   └── my-project/
│       ├── to-do/
│       ├── in-progress/
│       ├── pending-review/
│       └── done/
├── Project example.md               # Template for new projects
└── task template.md                 # Template for new tasks
```

## Project file format

Each `.md` file under `PROJECTS/` is one project:

```markdown
---
priority: 1
location: /abs/path/to/project/working/dir
use_git: true
---
# Goal
What you want done.
# Description
Short description of the project.
# Decisions Log
```

`# Decisions Log` is the AI's memory — it records past decisions, discarded
ideas, and failed attempts so future runs don't repeat them.

## Task file format

Each `.md` file in a kanban folder is one task:

```markdown
# Description
What to do.
```

When a task moves to `pending-review/`, the bot fills in:

```markdown
# Description
What to do.
# Summary of what was done
What was actually done.
# Location
local path or PR URL
```

Only the human moves tasks to `done/`. The bot never does.

## How the pick works

`picker.py` runs six gates in order:

1. **Claude usage gate.** Reads `~/.claude/rate-limit-cache.json` (written by
   the statusline hook) and skips if usage is `>= max_usage_pct`.
2. **PAUSED gate.** Projects whose `.md` filename matches a file in `PAUSED/`
   are dropped. Human-only — the bot never pauses projects.
3. **Frontmatter parse.** Files without `---`-delimited frontmatter are
   warned to stderr and dropped. Task folders are auto-created for projects
   that don't have them yet.
4. **In-progress gate.** If *any* project has a task in
   `TASKS/<name>/in-progress/`, that project is returned immediately so the
   loop can resume the unfinished task.
5. **Pending-Review gate.** Projects with `max_pending_review` or more files
   in `TASKS/<name>/pending-review/` are dropped. This caps unreviewed work
   per project.
6. **Idle gate.** `last_touched = max(git_last_commit,
   max_mtime_under(location))`. Projects touched in the last `idle_hours`
   are dropped. (`use_git: true` enables the git half; otherwise only mtime
   is considered.)

Survivors are sorted by `priority` ascending. On ties, the project markdown
file with the **oldest mtime** wins — the one whose project file
has been modified the longest ago.

Stdout is always one line:
- `READY: /abs/path/to/winner.md` — the worker task runs.
- `SKIP: <reason>` — the worker task is auto-skipped by the engine.

## What the bot does

When a project is picked, the bot:

1. Reads the project file, `# Goal`, and `# Decisions Log`
2. Picks the top task from `TASKS/<name>/to-do/` (or proposes a new one if
   the folder is empty)
3. Moves it to `in-progress/`, does the work, commits if `use_git: true`
4. Fills in summary and location, moves to `pending-review/`
5. Appends decisions, discarded ideas, and findings to `# Decisions Log`

## Files

- `conduit.yaml` — two-task DAG: `pick_project` (bash) → `loop_until_done` (conduit).
- `picker.py` — stdlib-only Python picker.
- `autonomous-projects-night.yaml` — schedule you can install.

## Manual run

```bash
atelier run autonomous-projects \
  --input projects_dir="/path/to/AUTONOMOUS_PROJECTS" \
  --input max_usage_pct=80 \
  --input idle_hours=2 \
  --input max_pending_review=3 \
  --input token_limit=19000000
```

All five inputs are required at run time. Edit
`autonomous-projects-night.yaml` for your preferred values.

## Schedule

```bash
atelier schedule add .atelier/conduits/autonomous-projects/autonomous-projects-night.yaml
atelier scheduler start    # foreground daemon; Ctrl+C to stop
```

## Machine-specific bits

- `conduit.yaml` references `picker.py` by absolute path. If you move this
  repo, update the `python3 ...picker.py` line.
- The schedule's `projects_dir` and `run_path` are machine-specific. Update
  `autonomous-projects-night.yaml` for your setup.
- `token_limit` is a coarse approximation of your Claude Code 5h quota.
  Tune it based on what `npx ccusage blocks` shows during a typical session.
