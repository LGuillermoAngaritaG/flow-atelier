# TODO: Extract `app/main.py` into `app/cli/`

Source spec: `SPEC.md`. Full plan: `tasks/plan.md`.

## Phase 1 — Foundation

- [ ] **Task 0** — Capture pre-refactor `--help` baseline into `tasks/baseline_help/`
- [ ] **Task 1** — Extract shared helpers to `app/cli/_shared.py`; re-import in `app/main.py`
- [ ] **Task 2** — Extract rendering helpers to `app/cli/render.py`; re-import in `app/main.py`
- [ ] **Task 3** — Scaffold `app/cli/` (empty stubs + `cli/main.py` Typer construction); re-root `app` so `app/main.py` imports it from `app.cli.main`

### Checkpoint A — Foundation
- [ ] `uv run pytest` green
- [ ] `uv run atelier --help` byte-identical to baseline
- [ ] Both `from app.main import app` and `from app.cli import app` return the same Typer with all 8 commands

## Phase 2 — Move commands (one slice each)

- [ ] **Task 4** — Move `init` (`init_cmd`, `HELLO_CONDUIT_YAML`) → `cli/init.py`
- [ ] **Task 5** — Move `run` (`run_cmd`) → `cli/run.py`
- [ ] **Task 6** — Move `status` (`status_cmd`) → `cli/status.py`
- [ ] **Task 7** — Move `logs` (`logs_cmd`, `_follow_logs`, `_LOG_SHOW_CHOICES`) → `cli/logs.py`
- [ ] **Task 8** — Move `list` sub-app (`list_conduits_cmd`, `list_flows_cmd`) → `cli/list.py`
- [ ] **Task 9** — Move `schedule` sub-app (4 commands + `_load_schedule_payload`, `_resolve_schedule`) → `cli/schedule.py`
- [ ] **Task 10** — Move `scheduler` sub-app (`scheduler_start_cmd`, `scheduler_status_cmd`) → `cli/scheduler.py` *(depends on Task 9)*
- [ ] **Task 11** — Move `serve` (`serve_cmd`) → `cli/serve.py`

### Checkpoint B — All commands moved
- [ ] `uv run pytest` green
- [ ] Every subcommand `--help` byte-identical to baseline
- [ ] `app/main.py` contains only re-exports — no command bodies

## Phase 3 — Finalize

- [ ] **Task 12** — Collapse `app/main.py` to 4-line shim; update `tests/test_init.py` and `tests/test_main.py` imports to canonical paths

### Checkpoint C — Done
- [ ] `app/main.py` ≤ 10 lines
- [ ] `uv run pytest` green
- [ ] Every subcommand `--help` byte-identical to baseline
- [ ] No file under `app/cli/` exceeds 250 lines
- [ ] `grep -rn "from app.main\|import app.main" app tests` returns at most the optional self-import in `app/main.py`
