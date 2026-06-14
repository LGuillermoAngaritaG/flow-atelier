# Developing flow-atelier

This document covers how to set up a development environment, run the
tests, and find your way around the codebase. For what flow-atelier is
and how to use it, see [README.md](./README.md).

## Prerequisites

- Python 3.13 or newer.
- [uv](https://docs.astral.sh/uv/) for dependency and environment
  management.

The AI harnesses (`harness:claude-code`, `harness:codex`, etc.) are
only needed to run conduits that use them or the `live` test suite.
Unit tests do not require any harness installed.

## Setup

```bash
git clone <repo-url>
cd flow-atelier
uv sync                       # create .venv and install runtime + dev deps
uv run pre-commit install     # wire the pre-commit (lint) hook
uv run pre-commit install --hook-type pre-push   # wire the pre-push (test) hook
```

`uv sync` installs the `dev` dependency group declared in
`pyproject.toml` (pytest, ruff, pre-commit, and friends).

Copy `.env.example` to `.env` if you need to override any
`ATELIER_*` setting locally; every variable has a sensible default,
so this is optional.

## Running tests

```bash
uv run pytest                 # full suite, live harness tests excluded
uv run pytest tests/modules   # a subdirectory
uv run pytest -k templating   # by keyword
```

Test configuration lives in `pyproject.toml` under
`[tool.pytest.ini_options]`:

- `asyncio_mode = "auto"` — async tests run without explicit
  decorators.
- `addopts = "-m 'not live'"` — the `live` marker is excluded by
  default.
- `timeout = 300` — per-test timeout via `pytest-timeout`.

### Live tests

Tests marked `live` exercise the real AI harness CLIs. They are slow
and cost tokens, so they are excluded by default. Run them explicitly
only when you have the relevant harness installed and authenticated:

```bash
uv run pytest -m live
```

## Linting and formatting

Ruff handles both lint and format (config in `pyproject.toml`,
line length 100, target `py313`):

```bash
uv run ruff check .           # lint
uv run ruff check --fix .     # lint and autofix
uv run ruff format .          # format
```

## Git hooks

Hooks are managed by [pre-commit](https://pre-commit.com)
(`.pre-commit-config.yaml`):

- **pre-commit** — runs `ruff --fix` on staged files.
- **pre-push** — runs the full `uv run pytest` suite.

The pre-push hook fails the push if the test run leaves the working
tree dirty (for example, if `uv` re-syncs `uv.lock`). Commit the
resulting changes rather than bypassing the hook.

## Project layout

The `flow_atelier` package is organized in layers: CLI on top, a
`core` facade that wires everything together, an execution `engine`,
and `services` for the pluggable pieces (executors, store, scheduler,
API).

```
flow_atelier/
├── main.py                     # console-script entry point -> cli app
├── cli/
│   ├── main.py                 # Typer app + sub-apps (list, schedule, scheduler)
│   ├── commands/               # one module per command (run, init, check, ...)
│   └── rendering/              # Rich output + multiline terminal input
├── core/
│   ├── atelier.py              # Atelier facade: wires store + executors + engine
│   └── settings.py             # AtelierSettings (env-driven, ATELIER_ prefix)
├── modules/
│   ├── engine.py               # DAG validation + concurrent task execution
│   ├── conditions.py           # depends_on parsing, match/not_match predicates
│   ├── templating.py           # {{inputs.x}} / {{task.output}} resolution
│   └── liveness.py             # detect hard-killed flows
├── schemas/                    # Pydantic models
│   ├── conduit.py              # Conduit, TaskDefinition, ToolType enum
│   ├── flow.py                 # flow id generation/parsing
│   ├── log.py / progress.py    # log entries, per-task progress
│   └── api.py / ws.py          # REST + WebSocket schemas
├── services/
│   ├── executor/               # one executor per tool/harness
│   │   ├── base.py             # ExecutorBase, FlowContext
│   │   ├── bash.py             # tool:bash
│   │   ├── hitl.py             # tool:hitl
│   │   ├── conduit.py          # tool:conduit (recursive)
│   │   └── harness.py          # the five ACP harnesses
│   ├── store/                  # conduit/flow persistence
│   │   ├── base.py             # StoreBase (abstract)
│   │   └── filesystem.py       # FilesystemStore (project + global dirs)
│   ├── scheduler/              # runner, schedule store, trigger evaluation
│   └── api/                    # FastAPI server, WebSocket manager + HITL bridge
└── routes/                     # HTTP/WS route handlers (conduits, flows, ...)

tests/                          # mirrors the package layout
├── cli/  core/  modules/  schemas/
└── services/  test_api/  fixtures/
```

## Architecture notes

### The facade

`core/atelier.py` is the single entry point that the CLI and API both
call. Its constructor builds:

- a `FilesystemStore` over the project `.atelier/` and the global
  `~/.atelier/` directories,
- the executor registry (a dict keyed by tool string),
- the `Engine`,
- and the scheduler's `ScheduleStore`.

### The engine

`modules/engine.py` takes a validated `Conduit` and runs it:

1. Validates the DAG — cycle detection, unknown dependency names, and
   regex syntax in conditional dependencies.
2. Resolves which tasks are ready (all `depends_on` satisfied) and
   runs them concurrently, bounded by `max_concurrency`.
3. Looks up an executor by the task's `tool` value and calls it.
4. Handles templating, conditional skips, loops (`repeat` +
   `until`/`while`), retries, and timeouts.

A task whose condition is not met is **skipped**, and the skip
propagates to its dependents.

### Executors

Each tool maps to an `ExecutorBase` subclass in `services/executor/`.
Executors implement `execute(...)` and `is_available()` (the
preflight readiness probe used by `atelier check` and at the start of
`atelier run`). The registry is built in `core/atelier.py`; the set
of valid tool names is the `ToolType` enum in `schemas/conduit.py`.

The five AI harnesses share one implementation in `harness.py` that
speaks the [Agent Client Protocol](https://agentclientprotocol.com)
over stdio. They differ only in their launch command, which can be
overridden via the `ATELIER_*_LAUNCH_CMD` environment variables (see
`.env.example`). Each harness reuses its own CLI's login; flow-atelier
never handles credentials.

### Adding a new tool

1. Add the value to `ToolType` in `schemas/conduit.py`.
2. Implement an `ExecutorBase` subclass in `services/executor/`.
3. Register it in the executor dict in `core/atelier.py`.

### Storage

`services/store/` abstracts all persistence behind `StoreBase`. The
only implementation is `FilesystemStore`, which resolves conduits
from the project directory first and the global directory second, and
writes every run under `.atelier/flows/<flow_id>/`.

### Scheduler and API

`services/scheduler/` runs conduits on a wall-clock schedule, reading
one YAML file per schedule. `services/api/` (FastAPI) exposes the REST
and WebSocket surface that `atelier serve` hosts, including the
WebSocket bridge that delivers human-in-the-loop prompts to a
connected client. Route handlers live in `routes/`.
