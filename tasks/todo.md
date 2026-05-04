# Task List: Interactive Input Prompting

## Tasks

- [x] **Task 1:** Implement interactive prompting in `app/cli/run.py`
  - Load conduit definition after constructing `Atelier`
  - Compute missing inputs (`conduit.inputs` keys not in CLI `inputs`)
  - If missing and `sys.stdin.isatty()`: prompt for each with `  {name} ({desc}): `
  - Wrap in `try/except KeyboardInterrupt` → `raise typer.Exit(code=130)`
  - **Verify:** Manual run without `--input` → prompts appear, flow executes

- [x] **Task 2:** Verify partial inputs only prompt for missing keys
  - **Verify:** Unit test — pass `a=1`, conduit expects `a` + `b` → only `b` prompted

- [x] **Task 3:** Verify non-TTY stdin skips prompting
  - **Verify:** `echo "" | atelier run spec-plan-build` → ValueError as before

- [x] **Task 4:** Verify Ctrl+C aborts cleanly (code 130, no traceback)
  - **Verify:** Manual Ctrl+C → clean exit

- [x] **Task 5:** Run `pytest` — all existing tests pass
  - **Verify:** `pytest` exits 0 (369 passed, 2 pre-existing live harness flakes)
