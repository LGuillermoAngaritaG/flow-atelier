# Templating

Two substitutions are resolved at **task start** (not parse time):

| Pattern                        | Resolves to                                                       |
|--------------------------------|-------------------------------------------------------------------|
| `{{inputs.<name>}}`            | A conduit input or a HITL-collected input.                        |
| `{{<task_name>.output}}`       | The string `output` of an upstream task (must be in `depends_on`).|

## `{{inputs.<name>}}`

Values come from:

1. `--input key=value` on the CLI (or the `inputs` map passed to a
   `tool:conduit` sub-call).
2. Any `tool:hitl` task that has completed before this one — its
   collected inputs are added to `context.inputs` by name, so downstream
   tasks can use `{{inputs.<name>}}` exactly like CLI-provided inputs.

```yaml
inputs:
  name: Who to greet

tasks:
  - greet:
      description: Echo a greeting
      task: "echo hello {{inputs.name}}"
      tool: tool:bash
      depends_on: []
```

```bash
atelier run hello --input name=world
```

## `{{<task_name>.output}}`

Refers to the string `output` of an upstream task. The referenced task
**must appear in `depends_on`** — otherwise the engine has no guarantee
the upstream has finished when this template renders.

```yaml
tasks:
  - fetch_version:
      description: Read current version
      task: "cat VERSION"
      tool: tool:bash
      depends_on: []

  - print_version:
      description: Show it
      task: "echo current is {{fetch_version.output}}"
      tool: tool:bash
      depends_on: [fetch_version]
```

!!! note "What is `output`?"
    For `tool:bash`, `output` is the merged stdout+stderr stream.
    For harness tasks, `output` is the full agent transcript for that
    turn (or all turns, in interactive mode).
    For `tool:hitl`, `output` is a YAML dump of the collected inputs.
    For `tool:conduit`, `output` is the child flow's final status line.

## Resolution rules

- Substitutions are **whole-string** — no escaping, no expressions.
- If a referenced input or upstream task doesn't exist, the task fails
  with a clear error rather than substituting an empty string.
- Resolution happens once, at the moment the engine hands the task to
  the executor. For `repeat: N` tasks, each iteration re-resolves.

## What templating is *not*

- Not a general expression language. There are no arithmetic, filters,
  or conditionals inside `{{ ... }}`.
- Not a YAML pre-processor. `{{ ... }}` lives inside string fields and
  is resolved at runtime, not when the file is parsed.
- Not recursive. `{{inputs.x}}` where `x` itself contains `{{...}}` is
  treated literally.

For conditional execution, see [Conditional dependencies](conditions.md).
