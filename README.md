![flow-atelier](./atelier.png)

# flow-atelier

**flow-atelier** is a CLI and async workflow engine for running reproducible
DAG-based workflows called **conduits**. A single run of a conduit is a
**flow**. Tasks whose dependencies are satisfied run concurrently via
`asyncio`, subject to a conduit-level concurrency cap.

Each task is dispatched to one of five executors:

| Tool                  | What it runs                                                     |
|-----------------------|------------------------------------------------------------------|
| `tool:bash`           | a shell command (via `asyncio.create_subprocess_shell`)          |
| `tool:hitl`           | prompts a human on stdin for one or more named inputs            |
| `tool:conduit`        | another conduit, as a nested flow                                |
| `harness:claude-code` | Claude Code via the [ACP](https://agentclientprotocol.com) adapter |
| `harness:codex`       | OpenAI Codex via the ACP adapter                                 |

Harnesses speak the **Agent Client Protocol** (ACP) over stdio, so they
get real bidirectional interaction: the agent can ask for permission, ask
the user a free-form question mid-turn, or run a multi-turn conversation.
Both harnesses reuse your existing local CLI configuration — project-level
`.claude/settings.json`, skills, subagents, hooks, MCP servers, CLAUDE.md
(for claude) and `~/.codex/config.toml`, auth, AGENTS.md (for codex).

In `interactive: true` mode, flow-atelier keeps the session open across
turns: if the agent ends a turn without emitting the `[ATELIER_DONE]`
marker, the executor prompts the user on the terminal for the next reply
and sends it back as the next user message. The loop terminates when the
marker appears in the agent's output.

## Install

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

Install `atelier` globally on your PATH so it runs from any directory
(similar to how `claude` and `codex` run anywhere):

```bash
git clone <this-repo> flow-atelier
cd flow-atelier
uv tool install .
```

You can also install directly from a remote:

```bash
uv tool install git+<repo-url>
```

To upgrade or uninstall later:

```bash
uv tool upgrade flow-atelier
uv tool uninstall flow-atelier
```

For local development inside the repo, a plain `uv sync` + `uv run atelier`
also works.

### Harness prerequisites

`harness:claude-code` and `harness:codex` launch ACP adapters published
by Zed via `npx`, so you need:

- **Node.js / `npx`** on your PATH.
- An authenticated Claude Code and/or Codex setup on this machine (the
  adapters reuse your `~/.claude` and `~/.codex` configuration, including
  auth, settings, skills, MCP servers, CLAUDE.md, and AGENTS.md).

On first use `npx` will download and cache the adapter packages:

- `@zed-industries/claude-code-acp`
- `@zed-industries/codex-acp`

To pin a custom version or point at a locally installed adapter, set
`ATELIER_CLAUDE_LAUNCH_CMD` / `ATELIER_CODEX_LAUNCH_CMD` to a JSON array
of argv (see `.env.example`).

## Quick start

Scaffold a project-local `.atelier/` with a hello-world conduit:

```bash
atelier init
```

This creates `.atelier/conduits/hello/conduit.yaml`. If `.atelier/` already
exists in the current directory, `init` leaves it alone.

Run it:

```bash
atelier run hello --input name=world
# flow_id: hello_7a3c9f2e_20260412T153004Z
```

Check status:

```bash
atelier status hello_7a3c9f2e_20260412T153004Z
```

List everything:

```bash
atelier list conduits
atelier list flows --conduit hello
```

## Conduit scopes

Conduits can live in two places:

- **Project**: `./.atelier/conduits/` — scaffolded by `atelier init`.
- **Global**: `~/.atelier/conduits/` — shared across all projects, auto-created
  on first run of any `atelier` command.

When you invoke `atelier run <name>`, atelier looks for the conduit in the
project first, then falls back to global. A project conduit with the same
name as a global one silently wins. `atelier list conduits` tags each entry
with `[project]` or `[global]` so you can see which copy is in effect.

Flows are **always project-local** — every `atelier run` writes to
`./.atelier/flows/` in the current working directory, regardless of which
scope the conduit came from.

Example: keep a general-purpose `deploy` conduit globally and override it
per project when a specific repo needs different steps.

## Commands

```
atelier init
atelier run <conduit> [--input key=value ...]
atelier status <flow_id>
atelier list conduits
atelier list flows [--conduit <name>]
```

## Conduit reference

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

### Templating

- `{{inputs.<name>}}` — conduit or HITL input, resolved at task start.
- `{{<task_name>.output>}}` — the string output of an upstream task. The
  referenced task must appear in `depends_on` so the engine has already
  completed it by the time the template is rendered.

### Conditional dependencies

```
<task>.output.match(<regex>)        # dependency met iff regex matches
<task>.output.not_match(<regex>)    # dependency met iff regex does NOT match
```

The regex is everything between the leftmost `(` and the last `)` — no
quoting required. Python's `re.search` is used.

If the condition is not met, the dependent task is **skipped** (not failed).
A skip does not trigger fail-fast. Any task that references a skipped task's
output — via `depends_on` or `{{task.output}}` — is also skipped.

### Loop predicates (`until` / `while`)

A task with `repeat > 1` can break out of its loop early via one of two
predicates (mutually exclusive — set at most one):

```
until: output.match(<regex>)       # break as soon as an output matches
until: output.not_match(<regex>)   # break as soon as no output matches
while: output.match(<regex>)       # loop while an output matches; break otherwise
while: output.not_match(<regex>)   # loop while no output matches; break otherwise
```

Iteration 1 always runs before the predicate is evaluated. Both fields
parse at conduit-load time — a malformed regex fails before the first
task starts. The regex grammar is the same as the dependency DSL above:
everything between the leftmost `(` and the final `)`, no quoting,
matched with `re.search`.

**Predicate scope** depends on the task type:

- Non-conduit tasks — the predicate sees the single iteration output.
- `tool:conduit` tasks — the predicate sees **every nested sub-task
  output of that iteration** and fires on any-match. This lets you wrap
  a multi-step conduit, retry it, and break the moment any internal
  step emits a signal — not just the conduit's aggregate output.

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

### HITL inputs

`tool:hitl` tasks define their own `inputs: {name: description}` map. At
runtime the executor prints the task's prompt, then asks for each input by
name with its description. The answers are:

1. Appended to the flow's `input.yaml` as **top-level** keys (on collision
   they overwrite existing values).
2. Added to `context.inputs` so downstream tasks can use
   `{{inputs.<name>}}` in addition to `{{<hitl_task>.output}}` (which is a
   YAML dump of the collected map).

### Harness interactive mode

When a harness task sets `interactive: true`, flow-atelier appends the
following instruction to every user message it sends to the agent:

> When — and only when — you are completely finished, output the exact
> token `[ATELIER_DONE]` to signal completion.

The executor keeps the ACP session open across turns:

1. Sends the (resolved + suffixed) task prompt as a `session/prompt`.
2. Streams the agent's response chunks to your terminal as they arrive.
3. If the chunk buffer now contains the marker, the task completes.
4. Otherwise it asks you for your next reply on the terminal and sends
   that back as the next user message (marker suffix re-appended).
5. Loop, bounded by an internal max-turns safety net.

Permission requests coming from the agent (e.g. "can I run this tool?")
are presented to you as a numbered menu; your choice is returned to the
agent as the permission outcome.

Non-interactive tasks run a single turn and return whatever the agent
streamed before `stop_reason`.

## Folder layout

The `.atelier` directory lives in the working directory where `atelier` is
invoked.

```
.atelier/
├── conduits/
│   └── <conduit_name>/conduit.yaml
└── flows/
    └── <flow_id>/                       # <conduit>_<uuid8>_<YYYYMMDDTHHMMSSZ>
        ├── input.yaml
        ├── logs.json                    # append-only task execution log
        ├── progress.json                # live per-task status
        └── flows/
            └── <child_flow_id>/...      # nested tool:conduit runs
```

## Development

Run the test suite:

```bash
uv run pytest                                  # fast unit suite only
uv run pytest tests/test_live_harness.py -v    # live ACP smoke tests
```

The live harness tests spawn the real Zed ACP adapters for Claude Code
and Codex via `npx`, so they cost tokens and need network + valid auth.
They're wrapped in a try/xfail so transient flakes don't break the suite.

## Architecture

```
app/
├── main.py                    # Typer CLI (thin)
├── core/
│   ├── atelier.py             # facade — wires everything
│   └── settings.py            # pydantic-settings (ATELIER_* env)
├── services/
│   ├── executor/              # ExecutorBase + bash / hitl / conduit / harness
│   └── store/                 # StoreBase + FilesystemStore
├── modules/
│   ├── engine.py              # async DAG engine
│   ├── templating.py          # {{inputs.x}} / {{task.output}} resolver
│   └── conditions.py          # depends_on parser + evaluator
└── schemas/                   # pydantic models (Conduit, Flow, Progress, ...)
```

The engine only depends on base classes (`StoreBase`, `ExecutorBase`) so
new tools or storage backends can be added without touching the engine.
