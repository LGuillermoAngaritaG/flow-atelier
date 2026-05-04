# Plan: Interactive Input Prompting for `atelier run`

## Summary

Single-file change to `app/cli/run.py` that prompts for missing conduit inputs
when stdin is a TTY. No new dependencies, no engine changes.

## Dependency Graph

```
Conduit schema (inputs: dict[str, str])
    ↓
Atelier.run_conduit(name, inputs) → store.read_conduit(name)
    ↓
Engine.run(conduit, inputs) → validates missing inputs
    ↓
CLI run_cmd() ← THIS IS WHERE WE INSERT PROMPTING
```

The prompting logic sits between `_parse_inputs()` and `atelier.run_conduit()`.
It needs access to `atelier.store.read_conduit(conduit_name)` to discover
declared inputs and their descriptions.

## Tasks (vertical slices)

### Task 1: Implement interactive prompting in `run_cmd`

**What:** After constructing `Atelier` and parsing CLI inputs, load the conduit
definition, compute missing keys, and prompt for each one if stdin is a TTY.

**Changes:**
- `app/cli/run.py`: Add `sys` import, load conduit via `atelier.store.read_conduit()`,
  compute missing keys, prompt in a loop with KeyboardInterrupt handling.

**Acceptance criteria:**
- `atelier run <conduit>` with no `--input` prompts for each missing input
- Prompt format: `  {name} ({description}): `
- Filled inputs are passed to `run_conduit`

**Verify:** Manual run without inputs → prompts appear, flow starts.

---

### Task 2: Ensure partial inputs only prompt for missing keys

**What:** If user passes `-i a=1` but conduit expects `a` and `b`, only `b`
is prompted.

**Acceptance criteria:**
- Only keys present in `conduit.inputs` but absent from CLI `inputs` are prompted
- Order follows `conduit.inputs` declaration order

**Verify:** Unit test with monkeypatched `input()` or `builtins.input`.

---

### Task 3: Non-TTY stdin skips prompting

**What:** When stdin is not a TTY (piped), prompting is skipped entirely,
preserving the existing ValueError from the engine.

**Acceptance criteria:**
- `echo "" | atelier run <conduit>` fails with "missing required inputs"
- No prompt is displayed

**Verify:** `echo "" | atelier run spec-plan-build` → error output as before.

---

### Task 4: Ctrl+C aborts cleanly

**What:** `KeyboardInterrupt` during prompting prints a newline and exits
with code 130.

**Acceptance criteria:**
- No Python traceback on Ctrl+C
- Exit code is 130

**Verify:** Manual Ctrl+C during prompt → clean exit.

---

### Task 5: Existing tests pass

**What:** Run `pytest` to confirm no regressions.

**Verify:** `pytest` → all green.

---

## Checkpoints

1. **After Task 1:** Core functionality works — manual test confirms prompting.
2. **After Task 3:** Both TTY and non-TTY paths are correct.
3. **After Task 5:** Full test suite passes — ready to commit.

## Risks

- None significant. The change is ~15 lines in one function, guarded by
  `sys.stdin.isatty()`, with the engine validation as defense-in-depth.
