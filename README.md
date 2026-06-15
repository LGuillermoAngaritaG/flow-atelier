![flow-atelier](./atelier.png)

# Flow Atelier:

## Flow Atelier is built on a simple premise: the world doesn't run on people, it runs on processes that people execute.
Ask someone to make anything, for example: the best yogurt in the world, what a person will do is that they'll research, experiment, and produce something average. The same is true of an AI agent. But give that person a clear, step-by-step recipe — and keep refining it over time — and you can reach the best yogurt in the world.
That's what Flow Atelier does. We help you build simple, repeatable instructions for getting something done the same way every time, then let anyone improve on them. It mirrors how real businesses actually work. Coca-Cola and Pepsi don't differ because their managers, lawyers, or engineers are fundamentally different people — they differ because their processes are different.
Flow Atelier gives you the tool to design and refine those processes. The difference: instead of people executing them, AI agents do the work.

## The words we use

A few terms show up everywhere in this document:

- **Conduit** — a recipe. An ordered set of steps written in a single
  YAML file.
- **Task** — one step in that recipe. A task runs a shell command,
  asks a person a question, calls an AI tool, or runs another conduit.
- **Flow** — one run of a conduit. Every run is saved to disk, so you
  can always go back and see exactly what happened.
- **Harness** — an AI coding tool (Claude Code, Codex, opencode,
  Copilot, Cursor) that a task can hand work to.
- **HITL** — "human in the loop": a step that pauses to ask a person a
  typed question, then continues with the answer.

## What can you build with it?

Any pipeline that can be described as an ordered sequence or graph of
steps. The two examples further down — a one-line greeter and a deploy
pipeline with a human approval gate — illustrate two possible shapes;
they are not prescriptive templates.

A non-exhaustive list of things people have built:

- **Chatbots and AI agents** that chain multiple turns of conversation
  with retries, branches, and fallbacks.
- **Multi-AI pipelines** in which one assistant drafts a specification,
  a second produces a plan, and a third executes it — or in which two
  assistants review the same change and a third synthesizes their
  feedback.
- **CI/CD-style pipelines** that clone a repository, run tests with
  retry, request an AI code review, ask a human for confirmation, and
  then deploy or roll back based on the result.
- **Scheduled jobs** such as daily reports, weekly syncs, or one-shot
  reminders at a specific time.
- **Polling loops with retry and backoff** that call an endpoint until
  it returns a success status or a rate limit lifts.
- **Human-in-the-loop automations** — flows that pause to ask the
  operator a typed question and resume with the answer.
- **Reusable building blocks** — one conduit invoking another, so a
  `deploy` conduit written once can be called from many higher-level
  pipelines.
- **Pure-shell automation with no AI at all** — flow-atelier works as
  a general-purpose task runner in this mode.

If a task can be described as a sequence or graph of steps, it can be
written as a conduit.

## How a conduit runs

You write a conduit YAML file and put it in
`.atelier/conduits/<name>/conduit.yaml`. When you run
`atelier run <name>`, flow-atelier:

1. Reads the YAML.
2. Looks at each task's `depends_on` list to figure out which tasks can
   start now and which have to wait.
3. Starts every ready task at the same time, up to a configurable
   limit (`max_concurrency`).
4. For each task, picks an executor based on the `tool:` field:

   | Tool                  | What it runs                                                       |
   |-----------------------|--------------------------------------------------------------------|
   | `tool:bash`           | a shell command                                                    |
   | `tool:hitl`           | prompts a human on the terminal for one or more named answers      |
   | `tool:conduit`        | another conduit, as a nested run                                   |
   | `harness:claude-code` | Claude Code (via the [ACP](https://agentclientprotocol.com) adapter)|
   | `harness:codex`       | OpenAI Codex (via the ACP adapter)                                 |
   | `harness:opencode`    | [opencode](https://opencode.ai)                                    |
   | `harness:copilot`     | GitHub Copilot CLI                                                 |
   | `harness:cursor`      | Cursor CLI                                                         |

5. Saves everything to disk under `.atelier/flows/<flow_id>/` — what
   ran, what each task printed, whether it succeeded, when it
   finished.

The five AI harnesses use each tool's **own login** that lives on your
machine. flow-atelier never sees, stores, or proxies any credentials.

## Install

### One-command install (no Python needed)

The quickest way. The script downloads a prebuilt `atelier` binary into
`~/.atelier/bin`, verifies its SHA-256 checksum against the published
release, and adds it to your `PATH`. It is safe to re-run to upgrade.

**macOS (Apple Silicon) / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/LGuillermoAngaritaG/flow-atelier/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/LGuillermoAngaritaG/flow-atelier/main/install.ps1 | iex
```

Prebuilt binaries are published for **Linux x86_64**, **macOS arm64
(Apple Silicon)**, and **Windows x86_64**. Intel Macs are not supported
(no Rosetta fallback exists for an arm64 binary). Open a new terminal
after installing so the updated `PATH` takes effect.

### Install with uv (for Python users)

If you have Python 3.13+ and [uv](https://docs.astral.sh/uv/), you can
install from PyPI instead:

```bash
uv tool install flow-atelier
uv tool upgrade flow-atelier      # upgrade later
uv tool uninstall flow-atelier    # remove
```

Either way, you end up with an `atelier` command on your `PATH`.

### Optional: AI harnesses

You only need to install the harness(es) for the AI tools you actually
plan to use. If you never use AI in your conduits, you can skip this
entire section.

- **`harness:claude-code`** — Node.js / `npx` on PATH, plus an
  authenticated `claude` setup (`~/.claude/...`). On first use `npx`
  downloads `@zed-industries/claude-code-acp`.
- **`harness:codex`** — Node.js / `npx` on PATH, plus an authenticated
  `codex` setup (`~/.codex/...`). On first use `npx` downloads
  `@zed-industries/codex-acp`.
- **`harness:opencode`** — the `opencode` binary on PATH.
- **`harness:copilot`** — the `copilot` binary on PATH (from the
  `@github/copilot` npm package).
- **`harness:cursor`** — Node.js / `npx` on PATH, plus the
  `cursor-agent` binary on PATH.

Each harness reuses its own CLI's config and login. To pin a custom
version or point at a different adapter, set the matching
`ATELIER_*_LAUNCH_CMD` environment variable to a JSON array of argv
(see `.env.example`).

## Quickstart

```bash
atelier init                                # creates .atelier/conduits/hello/
atelier run hello --input name=world        # runs it
atelier status <flow_id>                    # shows progress
atelier list flows --conduit hello          # lists previous runs
```

`atelier init` writes a one-line `hello` conduit that only runs a
shell command, so this works end-to-end before you install any AI
tool.

## Examples

The two conduits below are **illustrative, not prescriptive**. A
conduit can have one step or fifty, and any combination of shell, AI,
and human steps. The samples show one minimal conduit and one larger
one to demonstrate the range; the conduits you write will look
nothing like them.

### A simple conduit (`hello`)

The one-task conduit that `atelier init` creates. It runs a single
shell command:

```yaml
name: hello
description: Say hello
inputs:
  name: Who to greet
tasks:
  - greet:
      description: greet someone
      task: "echo hello {{inputs.name}}"
      tool: tool:bash
      depends_on: []
```

Run it with `atelier run hello --input name=world`.

### A bigger conduit (`deploy_pipeline`)

A six-step pipeline that combines shell commands, an AI review, a
human approval gate, retry loops, conditional branches, and a nested
sub-conduit. It illustrates what is possible — a chatbot, a daily
report, or an agent loop would look entirely different.

```yaml
name: deploy_pipeline           # must match the folder name
description: Build test deploy
timeout: 3600                   # seconds per task, default 3600
max_concurrency: 3              # max tasks running in parallel, default 3

inputs:
  repo_url: The git repo URL
  branch: Branch to deploy
  env: Target environment

tasks:
  - clone_repo:
      description: Clone
      task: "git clone -b {{inputs.branch}} {{inputs.repo_url}} /tmp/build"
      tool: tool:bash
      depends_on: []

  - run_tests:
      description: Run tests
      task: "cd /tmp/build && make test"
      tool: tool:bash
      depends_on: [clone_repo]
      repeat: 3                          # try up to 3 times
      until: output.match("PASS")        # ...stopping early on success

  - code_review:
      description: AI review
      task: |
        Review /tmp/build/src for security issues.
        End your response with exactly one of:
        VERDICT: APPROVE
        VERDICT: REJECT
      tool: harness:claude-code
      depends_on: [clone_repo]
      interactive: false

  - approve:
      description: human gate
      task: "I need a final confirmation"
      tool: tool:hitl
      depends_on:
        - run_tests
        - code_review.output.match(VERDICT:\s*APPROVE)
      inputs:
        confirm: "Type 'yes' to approve deploy"
        reason: "Short reason for the decision"

  - deploy:
      description: Run deploy sub-conduit
      task: deploy_to_env
      tool: tool:conduit
      depends_on: [approve]
      inputs:
        target_env: "{{inputs.env}}"
        build_path: /tmp/build

  - rollback:
      description: Rollback if review rejected
      task: "make rollback"
      tool: tool:bash
      depends_on:
        - code_review.output.not_match(VERDICT:\s*APPROVE)
```

Step by step:

- `clone_repo` runs first because nothing depends on it.
- `run_tests` and `code_review` both wait on `clone_repo`, then run
  in parallel.
- `run_tests` retries up to 3 times, stopping as soon as the output
  contains `PASS`.
- `code_review` asks Claude Code to review the code and end with
  either `VERDICT: APPROVE` or `VERDICT: REJECT`.
- `approve` only runs if Claude approved (`...match(VERDICT:\s*APPROVE)`).
  It asks the human two typed questions on the terminal.
- `deploy` only runs after the human approves, and calls another
  conduit (`deploy_to_env`) as a nested run.
- `rollback` only runs if Claude rejected. The two branches are
  mutually exclusive — the unmet branch is silently skipped, not
  failed.

## Conduit reference

A conduit has a `name`, a short `description`, an optional `inputs`
map, and a `tasks` list. Each task has a `name`, a `task` body, a
`tool` value, and a `depends_on` list.

### Templating

- `{{inputs.<name>}}` — a conduit input or HITL answer.
- `{{<task_name>.output}}` — the printed output of an earlier task.
  The earlier task must appear in `depends_on`.
- `{{loop.previous}}` — this task's output from its previous loop
  iteration (empty before the first iteration completes). Only valid on
  a looping task (`repeat > 1`).
- `{{loop.history}}` — every prior iteration of this task, rendered as
  numbered blocks. Only valid on a looping task (`repeat > 1`).

A missing `{{inputs.x}}` fails the task immediately; a reference to a
task that was skipped or hasn't completed skips the referencing task.

### Conditional dependencies

```
<task>.output.match(<regex>)        # dependency met if regex matches
<task>.output.not_match(<regex>)    # dependency met if regex does NOT match
```

The regex is everything between the leftmost `(` and the last `)` —
no quoting required. Python's `re.search` is used.

If a condition is not met, the task is **skipped**, not failed.
Anything that depends on a skipped task is also skipped.

### Loops (`repeat` + `until` / `while`)

A task with `repeat > 1` can break out of its loop early:

```
until: output.match(<regex>)       # break as soon as an output matches
until: output.not_match(<regex>)   # break as soon as no output matches
while: output.match(<regex>)       # loop while an output matches; break otherwise
while: output.not_match(<regex>)   # loop while no output matches; break otherwise
```

Set at most one of `until` / `while`. The first iteration always runs
before the predicate is checked.

For `tool:conduit` loops, the predicate sees **every nested sub-task
output of that iteration** and fires on any match.

```yaml
- retry_while_rate_limited:
    tool: tool:bash
    task: 'curl -s -o body -w "%{http_code}" https://api/x'
    repeat: 10
    while: output.match("^429$")

- run_until_test_passes:
    tool: tool:conduit
    task: build_and_test
    repeat: 5
    until: output.match("PASS")
```

### Retries and per-task timeout

- `retries: <n>` — if a task *fails*, re-run it up to `n` more times
  (default `0`). This is different from `repeat`, which loops a task
  that is *succeeding*.
- `timeout: <seconds>` — override the per-task time limit for one task.
  When omitted, the conduit-level `timeout` applies.

### Asking a human (`tool:hitl`)

A `tool:hitl` task declares its own `inputs: {name: description}`
map. At runtime flow-atelier prints the prompt, asks for each input
by name on the terminal, and saves the answers so downstream tasks
can use them as `{{inputs.<name>}}`.

### Long AI conversations (`interactive: true`)

When a harness task sets `interactive: true`, flow-atelier appends
this line to every message it sends to the AI:

> When — and only when — you are completely finished, output the exact
> token `[ATELIER_DONE]` to signal completion.

Then it keeps the conversation open: the AI replies, flow-atelier
streams the reply to your terminal, and if the AI didn't write
`[ATELIER_DONE]` yet, flow-atelier asks **you** for the next message
to send back. The loop ends when `[ATELIER_DONE]` shows up.

If the AI asks for permission to run a tool, you'll see a numbered
menu on the terminal; your choice is sent back as the answer.

Non-interactive tasks run one turn and stop.

## Where conduits live

Conduits can live in two places:

- **Project**: `./.atelier/conduits/` — scaffolded by `atelier init`.
- **Global**: `~/.atelier/conduits/` — shared across all projects.

When you run a conduit, flow-atelier checks the project folder first,
then the global folder. A project-level conduit silently overrides a
global one with the same name.

Flows are **always project-local** — every `atelier run` writes its
flow folder under `.atelier/flows/` in the current working directory.

## Commands

```
atelier init
atelier check [<conduit>]                              # validate conduit(s) without running
atelier run <conduit> [--input key=value ...] [--show-steps/--hide-steps]
atelier run --resume <flow_id>                         # resume a failed/crashed flow
atelier status <flow_id>
atelier logs <flow_id> [--task <name>] [--follow] [--json]
atelier outputs <flow_id> [--task <name>] [--json]    # read back a finished flow's results
atelier list conduits
atelier list flows [--conduit <name>]
atelier rm <flow_id> [--force] [--yes]                 # delete one flow run
atelier prune [--conduit <name>] [--older-than <days>] [--keep <n>]   # bulk-delete old flows

# scheduling
atelier schedule add <file.{json,yaml}>
atelier schedule list [--json]
atelier schedule remove <id-or-name>
atelier schedule run-now <id-or-name>
atelier scheduler start [--reload-interval 30] [--log-level INFO]
atelier scheduler status [--json]

# HTTP + WebSocket server
atelier serve [--host 127.0.0.1] [--port 8000] \
              [--reload-interval 30] [--cors-origin URL]* \
              [--log-level INFO]
```

## Running on a schedule

`atelier scheduler` runs conduits on a wall-clock schedule. Each
schedule is one YAML file under `.atelier/schedules/<name>.yaml`. The
daemon is one foreground process you can put under `systemd`,
`launchd`, or any supervisor.

To register a schedule, write a YAML file like the one below and run
`atelier schedule add <file>`:

```yaml
conduit_name: report
inputs:
  date: today
run_path: /abs/path
schedule:
  mode: recurring
  name: weekday mornings
  days: [1, 2, 3, 4, 5]
  times: ["06:00", "12:00"]
```

`days` are `1=Mon` .. `7=Sun`; `times` are `"HH:mm"` 24-hour strings.
One-shots use `mode: once` with a `run_at` ISO datetime instead of
`days` / `times`. `atelier schedule add` also accepts the same shape
in JSON if you prefer that format.

- New or removed schedules are picked up on the next reload tick
  (default 30s).
- One-shot schedules remember they fired, so a daemon restart never
  re-runs them.
- Each schedule runs at most one instance at a time; missed fires
  are coalesced.
- `atelier schedule run-now <id-or-name>` fires a schedule
  immediately, bypassing the daemon.

## HTTP API (`atelier serve`)

`atelier serve` boots a single process that hosts both the HTTP /
WebSocket API and the scheduler daemon. It is the entry point the
Flow Atelier visual frontend connects to.

| Method   | Path                       | Notes |
|----------|----------------------------|-------|
| `GET`    | `/conduits`                | List conduits |
| `GET`    | `/conduits/:name`          | Read one |
| `POST`   | `/conduits`                | Create (201 on success, 409 on collision) |
| `PATCH`  | `/conduits/:name`          | Partial update |
| `DELETE` | `/conduits/:name`          | Delete |
| `POST`   | `/conduits/open-path`      | Reveal flow run path in OS file explorer |
| `POST`   | `/tasks/run`               | Run an ad-hoc one-task conduit |
| `GET`    | `/schedules`               | List active schedules |
| `POST`   | `/schedules`               | Create |
| `DELETE` | `/schedules/:id`           | Soft-delete |
| `GET`    | `/flows`                   | List prior flows |
| `GET`    | `/flows/:id/logs`          | Per-flow log entries |
| `WS`     | `/ws/run-conduit`          | Run flows + HITL gates over a socket |

Binds to `127.0.0.1:8000` by default; pass `--host 0.0.0.0` to expose
on the LAN. `--cors-origin` is repeatable.

## Folder layout

The `.atelier` directory lives in the working directory where
`atelier` is invoked.

```
.atelier/
├── conduits/
│   └── <conduit_name>/conduit.yaml
├── schedules/
│   └── <schedule_name>.yaml                # one YAML file per schedule
├── scheduler_state.json                    # fired-once markers
└── flows/
    └── <flow_id>/                          # <YYYYMMDD>_<uuid8>_<conduit>
        ├── input.yaml                      # the inputs this run was given
        ├── logs.jsonl                      # append-only log, one JSON object per line
        ├── progress.json                   # live per-task status
        ├── outputs.yaml                    # per-task outputs (written as tasks finish)
        └── flows/
            └── <child_flow_id>/...         # nested tool:conduit runs
```

## Contributing

For test instructions, the project layout, and internal architecture
notes, see [DEVELOPMENT.md](./DEVELOPMENT.md).
