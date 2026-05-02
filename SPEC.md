# Spec: Extract `app/main.py` into `app/cli/`

## Objective

`app/main.py` is 1,108 lines — roughly 60% Rich-rendering helpers, 30%
command handlers, 10% Typer wiring. The python-development skill the
project follows describes `main.py` as a thin entry point; the file has
drifted well past that.

This refactor splits `app/main.py` into a new `app/cli/` package, one
module per Typer sub-app plus shared rendering and helpers. The entry
point `atelier = "app.main:app"` from `pyproject.toml` continues to work
without change.

**Pure code-organization refactor — zero behavior change.** Every CLI
command runs identically before and after; every existing test passes
without behavioral modification (some imports update).

### Why

- `main.py` no longer fits in one screen, one mental model, or one
  agent context window without significant noise.
- The current layout couples unrelated commands (e.g., `serve` and
  `status` share constants and helpers across 1,000 lines apart).
- New CLI surface (planned: more `schedule` operations, more `serve`
  flags) would push `main.py` further past the threshold.

## Tech Stack

No change. Existing dependencies only:

- Python 3.13+
- Typer 0.12+ (CLI framework)
- Rich 13.7+ (terminal rendering)
- Pydantic v2 / pydantic-settings (already used)

## Commands

No new commands. All existing commands retain their exact signatures,
flags, help text, and behavior:

```
atelier init
atelier run <conduit> [--input key=value ...]
atelier status <flow_id> [--json]
atelier logs <flow_id> [--task X] [--show output|stdout|stderr|all]
                       [--last N] [--follow] [--json]
atelier list conduits [--json]
atelier list flows [--conduit X] [--json]
atelier schedule add <file>
atelier schedule list [--json]
atelier schedule remove <ref>
atelier schedule run-now <ref>
atelier scheduler start [--reload-interval N] [--log-level X]
atelier scheduler status [--json]
atelier serve [--host H] [--port P] [--reload-interval N]
              [--cors-origin URL]* [--log-level X]
```

Verification commands:

```
Test:  uv run pytest
Lint:  (none configured — tracked separately)
Run:   uv run atelier --help
```

## Project Structure

New `app/cli/` package, peer to existing top-level packages:

```
app/
├── __init__.py
├── main.py                # thin shim: re-exports `app` for entry point compat
├── cli/                   # NEW: CLI presentation layer
│   ├── __init__.py        # re-exports `app` (the root Typer)
│   ├── main.py            # builds root Typer + add_typer wiring
│   ├── init.py            # `atelier init`
│   ├── run.py             # `atelier run`
│   ├── status.py          # `atelier status`
│   ├── logs.py            # `atelier logs` (+ follow loop)
│   ├── list.py            # `atelier list` sub-app (conduits, flows)
│   ├── schedule.py        # `atelier schedule` sub-app
│   ├── scheduler.py       # `atelier scheduler` sub-app
│   ├── serve.py           # `atelier serve`
│   ├── render.py          # shared Rich rendering (panels, tables, glyphs)
│   └── _shared.py         # shared helpers: console, parsing, formatting,
│                          # _resolve_flow_id, _schedule_store
├── core/                  # unchanged
├── modules/               # unchanged
├── routes/                # unchanged
├── schemas/               # unchanged
└── services/              # unchanged
```

`app/main.py` after refactor (whole file):

```python
"""Backwards-compat entry point for `atelier = app.main:app`."""
from app.cli import app

if __name__ == "__main__":
    app()
```

### Module ownership

| Module | Owns |
|---|---|
| `cli/main.py` | Root `typer.Typer()`, all `add_typer` wiring |
| `cli/init.py` | `init_cmd`, `HELLO_CONDUIT_YAML` |
| `cli/run.py` | `run_cmd` |
| `cli/status.py` | `status_cmd` |
| `cli/logs.py` | `logs_cmd`, `_follow_logs`, `_LOG_SHOW_CHOICES` |
| `cli/list.py` | `list_app`, `list_conduits_cmd`, `list_flows_cmd` |
| `cli/schedule.py` | `schedule_app`, all four `schedule_*_cmd`, `_load_schedule_payload`, `_resolve_schedule` |
| `cli/scheduler.py` | `scheduler_app`, `scheduler_start_cmd`, `scheduler_status_cmd` |
| `cli/serve.py` | `serve_cmd` |
| `cli/render.py` | `_render_task_event`, `_render_log_entry`, `_render_planned_table`, `_render_run_footer`, `_truncate_tail`, `_truncated_section`, `_build_failure_body`, `_task_status_summary`, `_FLOW_STATUS_STYLE`, `_TASK_STATUS_GLYPHS` |
| `cli/_shared.py` | `console`, `_parse_inputs`, `_resolve_flow_id`, `_parse_iso`, `_format_duration_seconds`, `_flow_duration_seconds`, `_format_clock`, `_format_next_fire`, `_schedule_store` |

The leading underscore on `_shared.py` signals "package-internal —
nothing outside `app.cli` should import from this." `render.py` does
not have an underscore because it's the seam where future surfaces
(JSON-RPC CLI, tests) might legitimately reach in.

## Code Style

Match the existing codebase. One illustrative snippet — `cli/run.py`
after the move:

```python
"""`atelier run` command."""
from __future__ import annotations

import asyncio

import typer

from app.cli._shared import console, _parse_inputs
from app.cli.main import app
from app.cli.render import _render_run_footer, _render_task_event
from app.core.atelier import Atelier
from app.schemas.log import TaskEvent


@app.command(
    "run",
    help="Start a new flow for the named conduit. Use --input key=value to pass inputs.",
)
def run_cmd(
    conduit_name: str = typer.Argument(..., help="Name of the conduit to run."),
    inputs_raw: list[str] = typer.Option(
        [], "--input", "-i", help="key=value input (repeatable).",
    ),
) -> None:
    """Start a new flow for the named conduit."""
    inputs = _parse_inputs(inputs_raw)
    atelier = Atelier()
    collected_events: list[TaskEvent] = []

    def _on_event(event: TaskEvent) -> None:
        collected_events.append(event)
        _render_task_event(event, console)

    captured_flow_id: dict[str, str | None] = {"id": None}

    def _on_started(fid: str) -> None:
        captured_flow_id["id"] = fid

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(
                conduit_name, inputs,
                on_task_event=_on_event,
                on_flow_started=_on_started,
            )
        )
    except Exception as e:  # noqa: BLE001
        _render_run_footer(collected_events, console)
        console.print(f"[red]flow failed:[/red] {e}")
        fid = captured_flow_id["id"]
        if fid:
            console.print(f"[red]flow_id:[/red] {fid}")
            console.print(f"[dim]→ atelier status {fid}[/dim]")
        raise typer.Exit(code=1)
    _render_run_footer(collected_events, console)
    console.print(f"[green]flow_id:[/green] {flow_id}")
```

### Conventions to keep

- `from __future__ import annotations` at top of every module.
- Underscore-prefix on package-internal helpers (`_parse_inputs`,
  `_resolve_flow_id`).
- Short docstrings; `:param:`/`:returns:` only on public functions
  (none here — all command handlers are Typer-decorated).
- Empty `__init__.py` except for `cli/__init__.py` which re-exports `app`.
- No new comments unless explaining a non-obvious WHY.

### Circular-import discipline

`cli/main.py` builds the root `app` and the sub-apps, then imports each
command module *after* construction so each module can `from app.cli.main
import app` at the top. The wiring sequence:

```python
# cli/main.py
import typer

app = typer.Typer(...)
list_app = typer.Typer(...)
schedule_app = typer.Typer(...)
scheduler_app = typer.Typer(...)
app.add_typer(list_app, name="list")
app.add_typer(schedule_app, name="schedule")
app.add_typer(scheduler_app, name="scheduler")

# Import-for-side-effect: each module decorates a command on `app` (or a sub-app)
from app.cli import init, run, status, logs, list as _list, \
                   schedule, scheduler, serve  # noqa: E402, F401
```

The `noqa: E402` is acceptable here — the imports must follow the Typer
construction. This is a single, contained, justified deviation.

## Testing Strategy

### Existing tests

Two test files import directly from `app.main`:

- `tests/test_main.py` — `from app.main import _render_task_event, _truncate_tail, app`
- `tests/test_init.py` — `from app.main import app`

**Decision: update tests to import from canonical locations.**

- `app` → `from app.cli import app` (or keep `from app.main import app`,
  since `app.main` re-exports it).
- `_render_task_event` → `from app.cli.render import _render_task_event`
- `_truncate_tail` → `from app.cli.render import _truncate_tail`

Updating tests to the canonical homes is preferred over re-exporting
internals from `app.main`. Internal helpers should not be part of
`app.main`'s public surface.

### No new tests required

This is a pure code-move refactor. The acceptance criterion is *the
existing test suite passes unchanged after import path updates*. No new
behavior, no new tests.

### Verification

```
uv run pytest                           # full unit suite passes
uv run atelier --help                   # root help renders, lists all subcommands
uv run atelier list conduits            # smoke: a non-trivial command runs
uv run atelier serve --port 0 &         # smoke: server boots
```

The existing `tests/test_api/test_serve_smoke.py` already covers the
serve smoke path.

## Boundaries

### Always do

- Keep behavior byte-identical: same flags, same help text, same exit
  codes, same stdout/stderr.
- Match existing style — `from __future__ import annotations`, type
  hints, minimal docstrings.
- Run `uv run pytest` after each task and confirm it stays green.

### Ask first before

- Renaming any command or flag.
- Changing the help text of any command.
- Adding new dependencies.
- Modifying `pyproject.toml` `[project.scripts]`.
- Re-exporting CLI internals from `app.main` (the spec says no — push
  back if a test seems to require it).
- Splitting any command body across multiple files (one command = one
  function in one file).

### Never do

- Add features, flags, or commands not in the existing CLI.
- Refactor logic inside a command body — only move it.
- Touch `app/core/`, `app/modules/`, `app/services/`, `app/schemas/`,
  or `app/routes/` — they are out of scope.
- Delete `app/main.py`. It must remain as the entry-point shim.
- Skip the `noqa: E402` discipline — imports inside `cli/main.py`
  follow Typer construction by design.

## Success Criteria

A reviewer can verify each of these independently:

1. `app/main.py` is ≤ 10 lines, contains only the entry-point shim.
2. `app/cli/` exists with the 11 modules listed in Project Structure.
3. `uv run pytest` passes (after test imports are updated to the new
   locations).
4. `uv run atelier --help` output is byte-identical to the pre-refactor
   output.
5. `uv run atelier <each subcommand> --help` output is byte-identical
   to pre-refactor.
6. `pyproject.toml` `[project.scripts]` is unchanged; `uv tool install
   .` still produces a working `atelier` binary.
7. No file under `app/cli/` exceeds 250 lines (rough sanity bound —
   `cli/serve.py` will be the largest).
8. No file imports from `app.main` other than the optional re-export
   inside `app.main` itself.

## Open Questions

None at spec time. Will surface in plan or implementation if found.

## Out of Scope (explicit non-goals)

The code review surfaced several real issues; none are addressed here.
Tracked separately:

- C1: `atelier serve` auth gate.
- I1: `WebSocketBroker.send` lock.
- I2: WS fire-and-forget task references.
- I3: `logs.json` JSONL switch.
- S2: Engine `run` method decomposition.

This refactor must not address any of them — surgical scope only.
