# Conduit YAML

A conduit is a YAML file at `.atelier/conduits/<name>/conduit.yaml`. The
folder name must match the `name` field inside the file.

## Full example

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
      repeat: 3                 # run sequentially 3 times

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

## Conduit-level fields

| Field             | Type               | Default | Description                                                  |
|-------------------|--------------------|---------|--------------------------------------------------------------|
| `name`            | `str`              | —       | Must match the folder name under `.atelier/conduits/`.       |
| `description`     | `str`              | —       | Free-form. First line is shown by `atelier list conduits`.   |
| `timeout`         | `int` (seconds)    | `3600`  | Per-task timeout applied by each executor.                   |
| `max_concurrency` | `int`              | `3`     | Max tasks the engine runs in parallel.                       |
| `inputs`          | `{name: desc}`     | `{}`    | Declared conduit inputs. Values come from `--input key=val`. |
| `tasks`           | list of task defs  | —       | At least one required. Task names must be unique.            |

## Task fields

Each task is a single-key dict whose key is the task name:

```yaml
- <task_name>:
    description: <str>
    task: <str>
    tool: <tool-type>
    depends_on: [<dep>, ...]
    repeat: <int>
    interactive: <bool>
    inputs: {<name>: <value-or-desc>}
```

| Field         | Type                | Default | Description                                                                     |
|---------------|---------------------|---------|---------------------------------------------------------------------------------|
| `description` | `str`               | —       | Free-form.                                                                      |
| `task`        | `str`               | —       | The payload. Its meaning depends on `tool` (see below).                         |
| `tool`        | enum                | —       | One of `tool:bash`, `tool:hitl`, `tool:conduit`, `harness:claude-code`, `harness:codex`. |
| `depends_on`  | list of `str`       | `[]`    | Upstream task names, optionally with regex conditions.                          |
| `repeat`      | `int ≥ 1`           | `1`     | Run the task sequentially N times. Useful for flaky tests / retries.            |
| `interactive` | `bool`              | `false` | Harness only — keeps the ACP session open across turns.                         |
| `inputs`      | `dict`              | `{}`    | HITL prompts (`{name: description}`) or sub-conduit inputs.                     |

### What `task` means per tool

| `tool`                | What `task` contains                                                           |
|-----------------------|--------------------------------------------------------------------------------|
| `tool:bash`           | A shell command string. Templated. Runs via `asyncio.create_subprocess_shell`. |
| `tool:hitl`           | A prompt shown to the human before their inputs are collected.                 |
| `tool:conduit`        | The **name** of another conduit to run as a nested flow.                       |
| `harness:claude-code` | The initial user message sent to Claude Code over ACP.                         |
| `harness:codex`       | The initial user message sent to Codex over ACP.                               |

## Validation

- Task names must be unique within a conduit.
- `repeat` must be ≥ 1.
- `name` field must match the folder name.
- Unknown fields on a task are rejected by pydantic.

See [Templating](templating.md), [Conditional dependencies](conditions.md),
[HITL inputs](hitl.md), and [Harness tasks](harnesses.md) for the
sub-specs each feature.
