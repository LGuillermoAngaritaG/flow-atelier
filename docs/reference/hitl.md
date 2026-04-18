# HITL inputs

`tool:hitl` tasks let you pause a flow to collect named inputs from the
human at the terminal. They double as **approval gates** (collect a
`confirm` input and condition downstream tasks on it) and as
**data ingress** (collect a commit message, a deploy target, etc.).

## Shape

```yaml
- approve:
    description: Human approval
    task: "I need a final confirmation before deploying."
    tool: tool:hitl
    depends_on: [run_tests, code_review]
    inputs:
      confirm: "Type 'yes' to approve deploy"
      reason: "Short reason for the decision"
```

- `task` is the **prompt** — printed once before inputs are collected.
- `inputs` is a `{name: description}` map — each entry becomes an
  interactive prompt asking for that named value.

## Runtime behavior

When the engine reaches a `tool:hitl` task, the executor:

1. Prints the task's `task` string as a banner.
2. For each entry in `inputs`, prompts with the description and reads
   one line from stdin.

The collected answers are then:

1. **Appended to the flow's `input.yaml` as top-level keys**. On
   collision with an existing conduit-level input, the HITL answer
   **overwrites** the previous value.
2. **Added to `context.inputs`** so downstream tasks can use
   `{{inputs.<name>}}` — exactly like CLI-provided inputs.
3. Also available as `{{<hitl_task>.output}}` — a YAML dump of the full
   collected map.

## Using HITL answers downstream

```yaml
tasks:
  - approve:
      description: Approve deploy
      task: "Gatekeeper: confirm before proceeding."
      tool: tool:hitl
      depends_on: []
      inputs:
        confirm: "Type 'yes' to approve"
        target_env: "Which env? (staging | prod)"

  - deploy:
      description: Deploy to the chosen env
      task: "make deploy ENV={{inputs.target_env}}"
      tool: tool:bash
      depends_on:
        - approve.output.match(confirm:\s*yes)
```

The `deploy` task reads the collected `target_env` via `{{inputs.target_env}}`,
and only runs if the collected `confirm` answer is exactly `yes`.

## Patterns

### Simple approval gate

```yaml
- approve:
    description: Approval gate
    task: "Ready to proceed?"
    tool: tool:hitl
    inputs:
      confirm: "Type 'yes' to proceed"

- next_step:
    ...
    depends_on:
      - approve.output.match(confirm:\s*yes)
```

### Collect a free-form message

```yaml
- commit_msg:
    description: Ask for a commit message
    task: "I need a commit message for this release."
    tool: tool:hitl
    inputs:
      message: "Commit message"

- tag:
    description: Tag the release
    task: "git tag -a v1.0.0 -m '{{inputs.message}}'"
    tool: tool:bash
    depends_on: [commit_msg]
```

### Branching on a choice

```yaml
- choose:
    description: Ask what to do
    task: "What do you want to do?"
    tool: tool:hitl
    inputs:
      action: "Type 'deploy' or 'rollback'"

- do_deploy:
    depends_on: [choose.output.match(action:\s*deploy)]
    ...

- do_rollback:
    depends_on: [choose.output.match(action:\s*rollback)]
    ...
```

## Caveats

- HITL tasks block the engine on stdin — you cannot run a flow with
  HITL tasks in a non-interactive environment (CI, cron) without
  providing the answers up front. A common workaround is to gate HITL
  tasks behind a conditional dependency that's only met in interactive
  contexts.
- Because HITL answers **overwrite** top-level keys in `input.yaml`, two
  HITL tasks with the same input name will have the later one win.
  Avoid name collisions.
