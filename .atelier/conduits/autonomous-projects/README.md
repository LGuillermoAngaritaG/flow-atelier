# autonomous-projects

A conduit that picks one project from its own project folders and advances it
via Claude Code. Projects and tasks live inside the conduit directory, so the
scaffold is self-contained — no external project directory to configure.

## Directory structure

```
.atelier/conduits/autonomous-projects/
├── projects/
│   ├── working/                     # One .md file per active project
│   │   └── my-project.md
│   └── paused/                      # Drop a project .md here to skip it
├── tasks/                           # Kanban folders per project
│   └── my-project/
│       ├── to-do/
│       ├── in-progress/
│       ├── pending-review/
│       └── done/
├── Project example.md               # Template for new projects
└── task template.md                 # Template for new tasks
```

Project files in `working/`/`paused/` and the `tasks/` kanban folders are
git-ignored (local-only); the templates and scaffold are tracked.

## Project file format

Each `.md` file under `projects/working/` is one project (see
`Project example.md`). The `location` may be an absolute path:

```markdown
---
location: /abs/path/to/project/working/dir
priority: 1
use_git: true
---
# Goal
What you want done.
# Description
Short description of the project.
# Constraints
Anything the bot must respect.
```

The project file is **owned by the human** — the bot treats it as read-only and
never edits it. The bot's cross-run memory comes from the task files in
`done/` and `pending-review/` (their `# What` and `# Validation process`), not
from the project file.

## Task file format

New tasks are created by copying `task template.md`. On creation the bot fills
in `# What`/`# Why`/`# How`:

```markdown
---
datetime:
location:
commits:
---
# What
The next step.
# Why
Why it matters.
# How
The plan.
# Validation process
```

When a task moves to `pending-review/`, the bot fills in the frontmatter
(`datetime` — completion date **and** time, e.g. `2026-06-05 14:32:07 CEST`;
`location` — local path or PR URL; and `commits`) and the
`# Validation process` section describing how the work was verified.

Only the human moves tasks to `done/`. The bot never does.

## How the pick works

`picker.py` runs six gates in order:

1. **Claude usage gate.** Reads `~/.claude/rate-limit-cache.json` (written by
   the statusline hook) and skips if usage is `>= max_usage_pct`.
2. **PAUSED gate.** Projects whose `.md` filename matches a file in
   `projects/paused/` are dropped. Human-only — the bot never pauses projects.
3. **Frontmatter parse.** Files without `---`-delimited frontmatter are
   warned to stderr and dropped. Task folders are auto-created for projects
   that don't have them yet.
4. **In-progress gate.** If *any* project has a task in
   `tasks/<name>/in-progress/`, that project is returned immediately so the
   loop can resume the unfinished task.
5. **Pending-Review gate.** Projects with `max_pending_review` or more files
   in `tasks/<name>/pending-review/` are dropped. This caps unreviewed work
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

1. Reads the project file (`# Goal`) — read-only — and skims past task
   files in `done/` and `pending-review/` for context
2. Picks the top task from `tasks/<name>/to-do/` (or proposes a new one from
   `task template.md` if the folder is empty)
3. Moves it to `in-progress/`, does the work, commits if `use_git: true`
4. Fills in the frontmatter and `# Validation process`, moves to `pending-review/`

## Files

- `conduit.yaml` — two-task DAG: `pick_project` (bash) → `loop_until_done` (conduit).
- `picker.py` — stdlib-only Python picker; defaults its root to this directory.

## Manual run

```bash
atelier run autonomous-projects
```

All five inputs declare a `default` in `conduit.yaml`, so none are required —
the command above runs with the recommended values (`max_usage_pct=80`,
`idle_hours=2`, `max_pending_review=3`, `token_limit=19000000`, and
`projects_dir` = this conduit's own directory). Override any of them with
`--input key=value`, e.g. `--input projects_dir=/path/that/has/projects-and-tasks`.

## Schedule

To run on a schedule, create a run-config yaml with a `schedule:` block (and any
inputs you want to override), then install it:

```bash
atelier schedule add path/to/your-schedule.yaml
atelier scheduler start    # foreground daemon; Ctrl+C to stop
```

## Machine-specific bits

- `conduit.yaml` references `picker.py` by a path relative to the run root
  (the repo root). If you run the conduit from elsewhere, adjust that path.
- The `location` field in each project file is machine-specific. The scaffold
  (projects/, tasks/) lives in this conduit by default, but `projects_dir` can
  point anywhere — just replicate the `projects/working`, `projects/paused`,
  `tasks` layout there.
- `token_limit` is a coarse approximation of your Claude Code 5h quota.
  Tune it based on what `npx ccusage blocks` shows during a typical session.
