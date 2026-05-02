# Implementation Plan: Extract `app/main.py` into `app/cli/`

## Overview

Pure code-organization refactor. Split the 1,108-line `app/main.py` into an
`app/cli/` package with one module per Typer sub-app plus shared rendering and
helpers. Zero behavior change. The `atelier = "app.main:app"` entry point in
`pyproject.toml` is unchanged; `app/main.py` becomes a 4-line re-export shim.

Source of truth: `SPEC.md`. Module ownership table at SPEC lines 110–122.

## Architecture Decisions

- **Single Typer instance, multiple decoration sites.** All `@app.command` and
  `@<sub>_app.command` decorators register against one root `app` defined in
  `cli/main.py`. Distributing decorations across files works because each
  module imports the same `app` object.
- **Side-effect imports in `cli/main.py`.** Sub-apps are constructed first,
  then each command module is imported at the bottom of `cli/main.py` (with
  `noqa: E402, F401`) so its decorator runs and registers the command.
- **Shim, don't relocate.** `app/main.py` stays as the entry point per
  `pyproject.toml`, but its body collapses to `from app.cli import app`.
- **Two-step migration to keep tests green throughout.** The bulk of the move
  happens in three foundation tasks (helpers → render → cli scaffold), after
  which each command's body is moved one-at-a-time, with the test suite green
  at every checkpoint.

## Dependency Graph

```
cli/_shared.py    ← uses: app.core, app.schemas, app.services
cli/render.py     ← uses: app.schemas (TaskEvent, Progress, FlowStatus, TaskStatus)
cli/main.py       ← defines: app, list_app, schedule_app, scheduler_app
                  ← imports (side-effect): all 8 command modules
cli/init.py       ← uses: cli.main.app
cli/run.py        ← uses: cli.main.app, cli._shared, cli.render, app.core, app.schemas
cli/status.py     ← uses: cli.main.app, cli._shared, cli.render, app.core, app.schemas
cli/logs.py       ← uses: cli.main.app, cli._shared, cli.render, app.core, app.schemas
cli/list.py       ← uses: cli.main.list_app, cli._shared, cli.render, app.core, app.schemas
cli/schedule.py   ← uses: cli.main.schedule_app, cli._shared, cli.render, app.schemas, app.services.scheduler
cli/scheduler.py  ← uses: cli.main.scheduler_app, cli._shared, cli.schedule.schedule_list_cmd, app.services.scheduler
cli/serve.py      ← uses: cli.main.app, cli._shared, app.core, app.services.api, app.services.scheduler
```

`scheduler.py` depends on `schedule.py` (its `status` reuses
`schedule_list_cmd`). All other command modules are mutually independent.

## Task List

### Phase 1 — Foundation (tests stay green)

- [ ] **Task 0: Capture pre-refactor `--help` baseline** — XS
- [ ] **Task 1: Extract shared helpers to `cli/_shared.py`** — S
- [ ] **Task 2: Extract rendering helpers to `cli/render.py`** — S
- [ ] **Task 3: Scaffold `cli/` package and re-root `app`** — M

#### Checkpoint A: Foundation in place
- [ ] `uv run pytest` — green
- [ ] `uv run atelier --help` — byte-identical to Task 0 baseline
- [ ] `from app.cli import app` works; `from app.main import app` still works

### Phase 2 — Move commands (one slice per task)

- [ ] **Task 4: Move `init` to `cli/init.py`** — S
- [ ] **Task 5: Move `run` to `cli/run.py`** — S
- [ ] **Task 6: Move `status` to `cli/status.py`** — S
- [ ] **Task 7: Move `logs` to `cli/logs.py`** — S
- [ ] **Task 8: Move `list` sub-app to `cli/list.py`** — S
- [ ] **Task 9: Move `schedule` sub-app to `cli/schedule.py`** — M
- [ ] **Task 10: Move `scheduler` sub-app to `cli/scheduler.py`** — S
- [ ] **Task 11: Move `serve` to `cli/serve.py`** — S

#### Checkpoint B: All commands migrated
- [ ] `uv run pytest` — green
- [ ] Each subcommand `--help` byte-identical to Task 0 baseline
- [ ] `app/main.py` contains only re-imports / re-exports — no command bodies

### Phase 3 — Finalize

- [ ] **Task 12: Collapse `app/main.py` to shim + update test imports** — S

#### Checkpoint C: Done
- [ ] `app/main.py` is ≤ 10 lines
- [ ] `uv run pytest` — green
- [ ] `uv run atelier --help` and every subcommand `--help` byte-identical
- [ ] No file in `app/cli/` exceeds 250 lines
- [ ] No file (except optionally `app/main.py` itself) imports from `app.main`

---

## Tasks

### Task 0: Capture pre-refactor `--help` baseline

**Description:** The success criterion is byte-identical `--help` output for
every command. Capture the pre-refactor reference now so every later task can
diff against it. No code changes.

**Acceptance criteria:**
- [ ] `tasks/baseline_help/` contains a help capture for `atelier`, every
  subcommand, and every sub-app subcommand.

**Verification:**
- [ ] Files exist and are non-empty.

**Dependencies:** None.

**Files likely touched:**
- `tasks/baseline_help/root.txt`
- `tasks/baseline_help/<each-command>.txt`

**Estimated scope:** XS.

**Commands to run:**
```
mkdir -p tasks/baseline_help
uv run atelier --help > tasks/baseline_help/root.txt
for c in init run status logs list schedule scheduler serve; do
  uv run atelier $c --help > tasks/baseline_help/$c.txt
done
uv run atelier list conduits --help > tasks/baseline_help/list-conduits.txt
uv run atelier list flows --help > tasks/baseline_help/list-flows.txt
uv run atelier schedule add --help > tasks/baseline_help/schedule-add.txt
uv run atelier schedule list --help > tasks/baseline_help/schedule-list.txt
uv run atelier schedule remove --help > tasks/baseline_help/schedule-remove.txt
uv run atelier schedule run-now --help > tasks/baseline_help/schedule-run-now.txt
uv run atelier scheduler start --help > tasks/baseline_help/scheduler-start.txt
uv run atelier scheduler status --help > tasks/baseline_help/scheduler-status.txt
```

---

### Task 1: Extract shared helpers to `cli/_shared.py`

**Description:** Create `app/cli/__init__.py` (empty package marker) and
`app/cli/_shared.py`. Move the helpers listed for `_shared.py` in the spec out
of `app/main.py` and re-import them back into `app/main.py` so the rest of
`main.py` continues to work unchanged. Tests still import the public `app`
from `app.main` — they don't touch these helpers — so they remain green.

**Functions/objects to move** (per SPEC line 121):
`console`, `_parse_inputs`, `_resolve_flow_id`, `_parse_iso`,
`_format_duration_seconds`, `_flow_duration_seconds`, `_format_clock`,
`_format_next_fire`, `_schedule_store`.

**Acceptance criteria:**
- [ ] `app/cli/__init__.py` exists (empty file).
- [ ] `app/cli/_shared.py` exists, contains exactly the 9 names above plus
  their imports, with `from __future__ import annotations` at the top.
- [ ] `app/main.py` re-imports these names from `app.cli._shared` — no
  duplicate definitions.
- [ ] No test file is touched.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier --help` — output diff against `tasks/baseline_help/root.txt` is empty.
- [ ] `uv run atelier list conduits` — runs without error.

**Dependencies:** Task 0.

**Files likely touched:**
- `app/cli/__init__.py` (new)
- `app/cli/_shared.py` (new)
- `app/main.py` (edit)

**Estimated scope:** S.

---

### Task 2: Extract rendering helpers to `cli/render.py`

**Description:** Move all rendering/glyph helpers to `app/cli/render.py` and
re-import them in `app/main.py`. `tests/test_main.py` imports
`_render_task_event` and `_truncate_tail` from `app.main` — those re-exports
must continue to resolve through `app/main.py` until Task 12 updates the
tests, so this task adds the re-import line.

**Functions/objects to move** (per SPEC line 120):
`_render_task_event`, `_render_log_entry`, `_render_planned_table`,
`_render_run_footer`, `_truncate_tail`, `_truncated_section`,
`_build_failure_body`, `_task_status_summary`, `_FLOW_STATUS_STYLE`,
`_TASK_STATUS_GLYPHS`.

**Acceptance criteria:**
- [ ] `app/cli/render.py` exists, contains exactly the 10 names above plus
  imports, with `from __future__ import annotations` at the top.
- [ ] `app/main.py` re-imports these names from `app.cli.render`.
- [ ] No test file is touched.

**Verification:**
- [ ] `uv run pytest` — green (specifically `tests/test_main.py` which
  references `_render_task_event` and `_truncate_tail`).
- [ ] `uv run atelier --help` — byte-identical to baseline.

**Dependencies:** Task 1.

**Files likely touched:**
- `app/cli/render.py` (new)
- `app/main.py` (edit)

**Estimated scope:** S.

---

### Task 3: Scaffold `cli/` package and re-root `app`

**Description:** Build `cli/main.py` with the root `Typer` and three sub-apps,
plus 8 empty command stubs. Then update `app/main.py` to import `app`,
`list_app`, `schedule_app`, `scheduler_app` from `cli/main.py` instead of
constructing them locally. The decorations still in `app/main.py` then attach
to the cli's `app`. Update `cli/__init__.py` to re-export `app`.

After this task: `from app.main import app` and `from app.cli import app`
return the same Typer instance, with all 8 commands still attached (because
their decorators in `app/main.py` ran against the imported `app`).

**Subtasks:**
1. Create empty stub files (each containing only `from __future__ import annotations`):
   `cli/init.py`, `cli/run.py`, `cli/status.py`, `cli/logs.py`,
   `cli/list.py`, `cli/schedule.py`, `cli/scheduler.py`, `cli/serve.py`.
2. Create `cli/main.py`:
   - Build `app = typer.Typer(...)`, `list_app`, `schedule_app`,
     `scheduler_app` with their existing help text.
   - `app.add_typer(...)` for the three sub-apps.
   - At the bottom, `from app.cli import init, run, status, logs, list as _list, schedule, scheduler, serve  # noqa: E402, F401`.
3. Update `cli/__init__.py` to `from app.cli.main import app  # noqa: F401`.
4. In `app/main.py`:
   - Remove the four `typer.Typer(...)` constructions.
   - Remove the three `app.add_typer(...)` calls.
   - Add `from app.cli.main import app, list_app, schedule_app, scheduler_app`.

**Acceptance criteria:**
- [ ] `app/cli/main.py` constructs the four Typers with help text byte-identical
  to the originals at SPEC-referenced lines 45–69.
- [ ] All 8 stub modules exist.
- [ ] `app/cli/__init__.py` re-exports `app`.
- [ ] `app/main.py` no longer constructs any Typer; it imports them.
- [ ] `python -c "from app.cli import app; print(len(app.registered_commands))"` reports
  the same count as `python -c "from app.main import app; ..."`.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier --help` and each subcommand `--help` — byte-identical to baseline.
- [ ] `uv run atelier list conduits` — runs without error.

**Dependencies:** Task 2.

**Files likely touched:**
- `app/cli/main.py` (new)
- `app/cli/__init__.py` (edit)
- `app/cli/{init,run,status,logs,list,schedule,scheduler,serve}.py` (new, stubs)
- `app/main.py` (edit)

**Estimated scope:** M.

---

### Tasks 4–11: Move each command (vertical slice)

**Shared pattern.** Each task is the same surgical move:

1. Cut the command function (and any command-private helpers/constants
   per the SPEC ownership table) from `app/main.py`.
2. Paste into the destination `cli/<module>.py`, with:
   - `from __future__ import annotations` at the top.
   - Imports for what the function uses (Typer, the cli `app` or sub-app,
     helpers from `cli._shared` and `cli.render`, plus app-internal modules).
3. Remove the corresponding re-imports from `app/main.py` only when nothing
   in `main.py` still references them.
4. Re-run pytest and the relevant `--help`.

After each task: behavior is unchanged because the decorator runs in the
imported module instead of in `main.py`, but the same `app` object accumulates
the command either way. Tests continue to pass because `from app.main import app`
returns the cli's `app` (Task 3 wired this).

---

### Task 4: Move `init` to `cli/init.py`

**Move:** `init_cmd`, `HELLO_CONDUIT_YAML`.

**Acceptance criteria:**
- [ ] `app/cli/init.py` contains `init_cmd` and `HELLO_CONDUIT_YAML`.
- [ ] `init_cmd` is gone from `app/main.py`.
- [ ] Decorator: `@app.command("init", help=...)` against `app` from `app.cli.main`.

**Verification:**
- [ ] `uv run pytest tests/test_init.py` — green.
- [ ] `uv run atelier init --help` — byte-identical to baseline.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/init.py`, `app/main.py`. Scope: S.

---

### Task 5: Move `run` to `cli/run.py`

**Move:** `run_cmd`.

**Acceptance criteria:**
- [ ] `app/cli/run.py` contains `run_cmd`, importing `console` and
  `_parse_inputs` from `app.cli._shared` and `_render_run_footer`,
  `_render_task_event` from `app.cli.render`.
- [ ] `run_cmd` is gone from `app/main.py`.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier run --help` — byte-identical to baseline.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/run.py`, `app/main.py`. Scope: S.

---

### Task 6: Move `status` to `cli/status.py`

**Move:** `status_cmd`.

**Acceptance criteria:**
- [ ] `app/cli/status.py` contains `status_cmd`.
- [ ] `status_cmd` is gone from `app/main.py`.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier status --help` — byte-identical to baseline.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/status.py`, `app/main.py`. Scope: S.

---

### Task 7: Move `logs` to `cli/logs.py`

**Move:** `logs_cmd`, `_follow_logs`, `_LOG_SHOW_CHOICES`.

**Acceptance criteria:**
- [ ] `app/cli/logs.py` contains the three names above.
- [ ] All three are gone from `app/main.py`.
- [ ] `_render_log_entry` is imported from `app.cli.render` (already there).

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier logs --help` — byte-identical to baseline.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/logs.py`, `app/main.py`. Scope: S.

---

### Task 8: Move `list` sub-app to `cli/list.py`

**Move:** `list_conduits_cmd`, `list_flows_cmd`. (`list_app` itself stays in
`cli/main.py`; this module just decorates it.)

**Acceptance criteria:**
- [ ] `app/cli/list.py` decorates `list_app` (imported from `app.cli.main`).
- [ ] Both `list_conduits_cmd` and `list_flows_cmd` are gone from `app/main.py`.

**Verification:**
- [ ] `uv run pytest` — green (test_main.py covers `list conduits`).
- [ ] `uv run atelier list conduits --help` and `list flows --help` — byte-identical.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/list.py`, `app/main.py`. Scope: S.

---

### Task 9: Move `schedule` sub-app to `cli/schedule.py`

**Move:** `schedule_add_cmd`, `schedule_list_cmd`, `schedule_remove_cmd`,
`schedule_run_now_cmd`, `_load_schedule_payload`, `_resolve_schedule`.

**Acceptance criteria:**
- [ ] `app/cli/schedule.py` contains the 6 names above.
- [ ] All 6 are gone from `app/main.py`.
- [ ] Decorators target `schedule_app` from `app.cli.main`.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier schedule {add,list,remove,run-now} --help` — byte-identical.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/schedule.py`, `app/main.py`. Scope: M.

---

### Task 10: Move `scheduler` sub-app to `cli/scheduler.py`

**Move:** `scheduler_start_cmd`, `scheduler_status_cmd`.

**Note:** `scheduler_status_cmd` calls `schedule_list_cmd` — keep that
behavior by adding `from app.cli.schedule import schedule_list_cmd`.

**Acceptance criteria:**
- [ ] `app/cli/scheduler.py` contains both functions.
- [ ] Both are gone from `app/main.py`.
- [ ] `scheduler_status_cmd` still delegates to `schedule_list_cmd`.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] `uv run atelier scheduler {start,status} --help` — byte-identical.

**Dependencies:** Task 9 (uses `schedule_list_cmd`).

**Files likely touched:** `app/cli/scheduler.py`, `app/main.py`. Scope: S.

---

### Task 11: Move `serve` to `cli/serve.py`

**Move:** `serve_cmd` and its inline `_lifespan`/`_run` definitions.

**Acceptance criteria:**
- [ ] `app/cli/serve.py` contains `serve_cmd`.
- [ ] `serve_cmd` is gone from `app/main.py`.
- [ ] File length ≤ 250 lines (sanity bound from SPEC success criterion 7).

**Verification:**
- [ ] `uv run pytest` — green (`tests/test_api/test_serve_smoke.py` covers serve).
- [ ] `uv run atelier serve --help` — byte-identical.

**Dependencies:** Task 3.

**Files likely touched:** `app/cli/serve.py`, `app/main.py`. Scope: S.

---

### Task 12: Collapse `app/main.py` to shim + update test imports

**Description:** With every command moved, `app/main.py` should now contain
only re-imports and re-exports. Strip everything; collapse to the 4-line shim
described in SPEC line 99. Update the two tests that import from `app.main`
to use canonical paths.

**`app/main.py` final content (whole file):**
```python
"""Backwards-compat entry point for `atelier = app.main:app`."""
from app.cli import app

if __name__ == "__main__":
    app()
```

**Test updates:**
- `tests/test_init.py:8` — `from app.main import app` → `from app.cli import app`.
  (Optional; the shim re-exports, so the existing import also works. Prefer the
  canonical import per SPEC line 246.)
- `tests/test_main.py:9` — split the import:
  - `from app.cli import app`
  - `from app.cli.render import _render_task_event, _truncate_tail`

**Acceptance criteria:**
- [ ] `app/main.py` is ≤ 10 lines.
- [ ] No imports from `app.main` remain anywhere in the repo (except optionally
  inside `app.main` itself).
- [ ] `tests/test_init.py` and `tests/test_main.py` import from canonical paths.
- [ ] No file under `app/cli/` exceeds 250 lines.

**Verification:**
- [ ] `uv run pytest` — green.
- [ ] For each baseline file, `diff <(uv run atelier <cmd> --help) tasks/baseline_help/<cmd>.txt`
  produces no output.
- [ ] `uv run atelier serve --port 0` boots and exits on Ctrl-C (or rely on
  `tests/test_api/test_serve_smoke.py`).
- [ ] `grep -rn "from app.main\|import app.main" app tests` returns at most the
  optional self-import inside `app/main.py`.

**Dependencies:** Tasks 4–11.

**Files likely touched:**
- `app/main.py` (collapsed)
- `tests/test_init.py` (edit)
- `tests/test_main.py` (edit)

**Estimated scope:** S.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Decoration order changes alter help output (e.g. command order in `--help`) | Medium — would break the byte-identical success criterion | Task 3 keeps the side-effect import order in `cli/main.py` matching the original decoration order in `app/main.py` (`init, run, status, logs, list, schedule, scheduler, serve`). |
| Circular import between `cli/main.py` and the command modules | High — would break the entry point | The pattern is exactly what the SPEC's "circular-import discipline" section describes: build all Typers first, import command modules at the bottom with `noqa: E402`. Each command module imports `app` (or a sub-app) from `cli.main`, never the reverse. |
| `scheduler_status_cmd` calls `schedule_list_cmd` directly — dependency between modules | Low | Task 10 follows Task 9; the import is a normal top-of-file `from app.cli.schedule import schedule_list_cmd`. |
| Tests importing `_render_task_event`/`_truncate_tail` from `app.main` break mid-refactor | Medium | Task 2 re-exports these from `app.main` until Task 12 updates the tests. |
| Stray `from app.main import …` in test_api or core | Low | Pre-checked: only `tests/test_init.py` and `tests/test_main.py` import from `app.main`. |
| `cli/serve.py` exceeds 250 lines | Low | Original `serve_cmd` is ~90 lines including helpers; well under the cap. |

## Open Questions

None at plan time. Will surface during implementation if found.

## Out of Scope

Per SPEC lines 320–331: C1 serve auth gate, I1 WS broker lock, I2 WS task
references, I3 logs.json JSONL switch, S2 engine `run` decomposition. Do not
address any of these in this refactor.
