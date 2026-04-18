# Conduit scopes

Conduits can live in two places:

- **Project**: `./.atelier/conduits/` — scaffolded by `atelier init`.
- **Global**: `~/.atelier/conduits/` — shared across all projects,
  auto-created on first run of any `atelier` command.

When you invoke `atelier run <name>`, atelier looks for the conduit in
the project first, then falls back to global. A project conduit with
the same name as a global one **silently wins**.

`atelier list conduits` tags each entry with `[project]` or `[global]`
so you can see which copy is in effect.

## Flows are always project-local

Every `atelier run` writes to `./.atelier/flows/` in the current working
directory, regardless of which scope the conduit came from.

This keeps reproducibility local: the directory you ran the command
from is the directory that holds the artifacts.

## When to use each scope

**Use global conduits for:**

- General-purpose utilities you want available in every repo
  (e.g. a `code-review` conduit that runs Claude Code on a path).
- Team-wide standard pipelines you installed once.

**Use project conduits for:**

- Workflows specific to one repo's build/test/deploy shape.
- Overrides of a global conduit when one project needs different steps
  under the same name.

!!! example "Override pattern"
    Keep a general-purpose `deploy` conduit in `~/.atelier/conduits/deploy/`.
    In a repo that needs different deploy steps, create
    `./.atelier/conduits/deploy/conduit.yaml` — it will win for any
    `atelier run deploy` invoked from that repo.
