# Hello world

The minimal viable conduit: one `tool:bash` task that echoes a greeting
built from a single input. `atelier init` creates this for you.

## Scenario

Prove that installation works and that `{{inputs.x}}` substitution is
happening. Nothing more.

## The conduit

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

## Run it

```bash
atelier run hello --input name=world
```

## What you should see

```
✓ greet [tool:bash]  exit=0 · 0.0s
hello world
flow_id: hello_7a3c9f2e_20260412T153004Z
```

- The green `✓` panel is the live render of the `greet` task.
- The body (`hello world`) is its merged stdout+stderr.
- `flow_id` is the id you pass to `atelier status` / `atelier logs`.

## What's on disk

```
.atelier/flows/hello_7a3c9f2e_20260412T153004Z/
├── input.yaml          # { name: world }
├── progress.json       # greet: completed
└── logs.json           # one entry: stdout="hello world\n", exit=0
```

## Variations

### Multiple inputs

```yaml
inputs:
  first: First name
  last: Last name
tasks:
  - greet:
      task: "echo hello {{inputs.first}} {{inputs.last}}"
      tool: tool:bash
      depends_on: []
```

```bash
atelier run hello --input first=Ada --input last=Lovelace
```

### Run 3 times

```yaml
- greet:
    task: "echo hello {{inputs.name}}"
    tool: tool:bash
    depends_on: []
    repeat: 3
```

Each iteration renders as `✓ greet [tool:bash] (1/3)`, `(2/3)`, `(3/3)`
and is logged as a separate entry in `logs.json`.
