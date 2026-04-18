# Architecture

flow-atelier is split into a thin CLI, a facade, an async DAG engine, a
set of executors, and a storage backend. The engine only depends on base
classes so new tools or storage backends can slot in without touching
the scheduler.

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

## Layers

### `main.py` — CLI

Typer app exposing `init`, `run`, `status`, `logs`, `list conduits`, and
`list flows`. Delegates all business logic to the `Atelier` facade.

### `core/atelier.py` — Facade

Wires a concrete `Store` + `Executor` registry into the `Engine`.
The CLI never talks to the engine directly.

### `modules/engine.py` — Async DAG engine

- Walks the task graph and dispatches each ready task to its executor.
- Respects the conduit's `max_concurrency` cap via an `asyncio.Semaphore`.
- Persists per-task progress and an append-only event log on every state
  change.
- Handles skip propagation when a conditional dependency evaluates false.

### `services/executor/` — Executors

Each executor implements `ExecutorBase.run(task, context) -> TaskResult`:

- `tool:bash` — shell command via `asyncio.create_subprocess_shell`.
- `tool:hitl` — prompts the user on stdin for the task's named inputs.
- `tool:conduit` — runs another conduit as a nested flow.
- `harness:claude-code` / `harness:codex` — spawn the Zed ACP adapter
  and drive it over stdio.

### `services/store/` — Storage

`FilesystemStore` is the default backend. Conduits live in
`./.atelier/conduits/` or `~/.atelier/conduits/`; flows always live in
`./.atelier/flows/<flow_id>/`.

Because the engine only sees `StoreBase`, a SQLite or S3-backed store
could be added without touching the scheduler.

## Concurrency model

- Independent tasks run in parallel, bounded by the conduit's
  `max_concurrency` (default 3).
- A task is **ready** when every entry in its `depends_on` is either
  completed (unconditional) or passes its regex (conditional).
- If a task is skipped, every downstream task that references it is
  transitively skipped — skips never trigger fail-fast.
- When a task fails and the flow is not in fail-fast mode, the engine
  continues running independent branches and marks dependents as
  `cancelled`.

## Data flow

```
conduit.yaml           ─┐
CLI --input key=value  ─┼─→ Engine ─→ Executor ─→ TaskResult
upstream task outputs  ─┘                          │
                                                   ▼
                              progress.json   logs.json   (child flows)
```

- Inputs arrive from the CLI and from any `tool:hitl` task's answers.
- Templating resolves `{{inputs.x}}` and `{{task.output}}` at task start.
- Every task writes a `LogEntry` (stdout, stderr, merged output, exit
  code, duration) to `logs.json` for later inspection with `atelier logs`.
