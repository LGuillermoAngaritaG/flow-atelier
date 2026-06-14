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
│       ├── ideas/                   # Bot writes idea_*.md / review_*.md proposals here
│       ├── bad_ideas/               # Human drops rejected proposals (+ reasoning) here
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

`picker.py` runs five gates in order:

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
5. **Idle gate.** `last_touched = max(git_last_commit,
   max_mtime_under(location))`. Projects touched in the last `idle_hours`
   are dropped. (`use_git: true` enables the git half; otherwise only mtime
   is considered.)

Survivors are sorted by `priority` ascending. On ties, the project markdown
file with the **oldest mtime** wins — the one whose project file
has been modified the longest ago.

Stdout is `SKIP: <reason>` (worker auto-skipped) or three lines —
`READY: /abs/path/to/winner.md`, `NAME: <stem>`, `LOCATION: <codebase dir>` —
that the resolver tasks consume.

### Pending-review cap (work-only)

The `max_pending_review` cap is **not** a picker gate — it does not drop the
project from selection. It is enforced by the conduit's `pr_gate` task, which
pauses only `work_task` (to-do execution) once `pending-review/` holds
`max_pending_review` or more files. Idea/review generation keeps running, so a
project with a full review backlog still accumulates proposals; only new
implementation pauses until you clear the backlog.

## The loop is human-in-the-loop

The bot never decides *what* is worth doing or *when* work is finished — those
judgments stay with the human:

1. **Bot proposes.** Each tick, the bot generates one idea and one review into
   `tasks/<name>/ideas/` (`idea_*.md`, `review_*.md`).
2. **Human triages.** You move each proposal into `tasks/<name>/bad_ideas/`
   (rejected — leave your reasoning in the file so future generation avoids that
   kind) or into `tasks/<name>/to-do/` (approved — becomes work).
3. **Bot executes.** The bot works only existing `to-do/`/`in-progress/` tasks. It
   never proposes or creates tasks itself. It moves a task to `in-progress/`, does
   the work, commits if `use_git: true`, fills in the frontmatter and
   `# Validation process`, then moves it to `pending-review/`.
4. **Human approves.** Only the human moves a task to `done/`.

### Idea/review generation

Generation is delegated to two nested conduits, `generate-idea` and
`generate-review`, run per tick while under the `max_ideas` cap (the combined count
of `idea_*.md` + `review_*.md` in `ideas/`). Each produces one plain-language
proposal plus a deeper plan. Rejected proposals in `bad_ideas/` steer future
generation away from that kind.

## What the bot does when executing a task

When a project is picked and it has a `to-do`/`in-progress` task, the bot:

1. Reads the project file (`# Goal`) — read-only — and skims past task
   files in `done/` and `pending-review/` for context
2. Picks the top task from `tasks/<name>/to-do/` (or resumes `in-progress/`)
3. Moves it to `in-progress/`, does the work, commits if `use_git: true`
4. Fills in the frontmatter and `# Validation process`, moves to `pending-review/`

## Files

- `conduit.yaml` — DAG: `pick_project` (bash) → `resolve_*` (bash) → `gen_gate` →
  `generate_idea`/`generate_review` (conduits); and `check_todo` + `pr_gate` →
  `work_task` (the `task-with-review` conduit, looped until a DONE verdict).
- `picker.py` — stdlib-only Python picker; defaults its root to this directory.
  Emits `READY:`/`NAME:`/`LOCATION:` lines the resolver tasks consume.

## Manual run

```bash
atelier run autonomous-projects
```

All six inputs declare a `default` in `conduit.yaml`, so none are required —
the command above runs with the recommended values (`max_usage_pct=80`,
`idle_hours=2`, `max_pending_review=10`, `token_limit=19000000`, `max_ideas=20`,
and `projects_dir` = this conduit's own directory). Override any of them with
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
