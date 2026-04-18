# Quickstart

This walks you from an empty directory to a finished flow with inspectable
logs in about a minute.

## 1. Scaffold a project

```bash
mkdir my-workflows && cd my-workflows
atelier init
```

This creates `.atelier/conduits/hello/conduit.yaml` — a minimal
hello-world conduit with a single `tool:bash` task. If `.atelier/`
already exists in the current directory, `init` leaves it alone.

The generated conduit looks like this:

```yaml title=".atelier/conduits/hello/conduit.yaml"
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

## 2. Run the flow

```bash
atelier run hello --input name=world
```

You should see a live-rendered panel for the `greet` task and a final
`flow_id:` line like:

```
✓ greet [tool:bash]  exit=0 · 0.0s
hello world
flow_id: hello_7a3c9f2e_20260412T153004Z
```

The flow id is composed of `<conduit>_<uuid8>_<UTC-timestamp>`. Every id
is unique per run.

## 3. Inspect the flow

```bash
atelier status hello_7a3c9f2e_20260412T153004Z
```

You can use any unique prefix — e.g. `atelier status hello_7a`. If the
prefix is ambiguous, `atelier` lists the matching ids and exits.

To dump all recorded stdout/stderr for a flow:

```bash
atelier logs hello_7a
atelier logs hello_7a --show all
atelier logs hello_7a --task greet
atelier logs hello_7a --follow   # tail mode; exits when the flow finishes
```

## 4. List what you have

```bash
atelier list conduits
atelier list flows
atelier list flows --conduit hello
```

`list conduits` tags each entry with `[project]` or `[global]` so you can
see which copy is in effect (see [Conduit scopes](../concepts/scopes.md)).

## Next steps

- Learn the full [conduit YAML spec](../reference/conduit.md).
- Wire in a human approval step with [HITL inputs](../reference/hitl.md).
- Drop in an AI agent task with a [harness](../reference/harnesses.md).
- Browse the [examples](../examples/index.md) to see real-world patterns.
