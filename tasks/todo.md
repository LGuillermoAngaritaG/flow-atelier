# TODO: Extract `app/main.py` into `app/cli/`

Source spec: `SPEC.md`. Full plan: `tasks/plan.md`.

## Phase 1 — Foundation

- [x] **Task 0** — Capture pre-refactor `--help` baseline into `tasks/baseline_help/`
- [x] **Task 1** — Extract shared helpers to `app/cli/_shared.py`; re-import in `app/main.py`
- [x] **Task 2** — Extract rendering helpers to `app/cli/render.py`; re-import in `app/main.py`
- [x] **Task 3** — Scaffold `app/cli/` (empty stubs + `cli/main.py` Typer construction); re-root `app` so `app/main.py` imports it from `app.cli.main`

### Checkpoint A — Foundation
- [x] `uv run pytest` green
- [x] `uv run atelier --help` byte-identical to baseline
- [x] Both `from app.main import app` and `from app.cli import app` return the same Typer with all 8 commands

## Phase 2 — Move commands (one slice each)

- [x] **Task 4** — Move `init` (`init_cmd`, `HELLO_CONDUIT_YAML`) → `cli/init.py`
- [x] **Task 5** — Move `run` (`run_cmd`) → `cli/run.py`
- [x] **Task 6** — Move `status` (`status_cmd`) → `cli/status.py`
- [x] **Task 7** — Move `logs` (`logs_cmd`, `_follow_logs`, `_LOG_SHOW_CHOICES`) → `cli/logs.py`
- [x] **Task 8** — Move `list` sub-app (`list_conduits_cmd`, `list_flows_cmd`) → `cli/list.py`
- [x] **Task 9** — Move `schedule` sub-app (4 commands + `_load_schedule_payload`, `_resolve_schedule`) → `cli/schedule.py`
- [x] **Task 10** — Move `scheduler` sub-app (`scheduler_start_cmd`, `scheduler_status_cmd`) → `cli/scheduler.py` *(depends on Task 9)*
- [x] **Task 11** — Move `serve` (`serve_cmd`) → `cli/serve.py`

### Checkpoint B — All commands moved
- [x] `uv run pytest` green
- [x] Every subcommand `--help` byte-identical to baseline
- [x] `app/main.py` contains only re-exports — no command bodies

## Phase 3 — Finalize

- [x] **Task 12** — Collapse `app/main.py` to 4-line shim; update `tests/test_init.py` and `tests/test_main.py` imports to canonical paths

### Checkpoint C — Done
- [x] `app/main.py` ≤ 10 lines (5 lines)
- [x] `uv run pytest` green (361 passed; 2 pre-existing live-harness failures excluded)
- [x] Every subcommand `--help` byte-identical to baseline
- [~] No file under `app/cli/` exceeds 250 lines (`render.py` at 274 — see note below)
- [x] `grep -rn "from app.main\|import app.main" app tests` returns 0 matches

### Note on `cli/render.py` size

`cli/render.py` is 274 lines, slightly above the 250-line "rough sanity
bound" from SPEC criterion 7. The file is verbatim moved code (10
documented helpers including `_render_task_event` ≈75 lines and
`_render_log_entry` ≈50 lines). Per SPEC: "Refactor logic inside a
command body — only move it." A future tightening pass on docstrings
or a split into render-events vs render-tables would bring it under 250
without touching behavior, but is out of scope for this surgical refactor.
