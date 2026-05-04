# SPEC: Interactive Input Prompting for `atelier run`

## Objective

When a user runs `atelier run <conduit>` without providing all required `--input` flags, the CLI should interactively prompt for each missing input instead of failing with an error. Each prompt displays the input's **name** and **description** (as declared in the conduit's `inputs: dict[str, str]`).

Users who prefer non-interactive usage can still pass all inputs inline via `--input key=value`.

## Current Behavior

```
$ atelier run spec-plan-build
flow failed: missing required inputs: ['task']
```

The engine (`app/modules/engine.py:130-132`) raises `ValueError` for any missing key. The CLI catches it and exits with code 1.

## Desired Behavior

```
$ atelier run spec-plan-build
  task (One-paragraph description of the task to spec, plan, and build.): my task here
flow_id: spec-plan-build_abc123_20260503T...
```

- If all inputs are provided via `--input`, no prompting occurs (unchanged).
- If some inputs are provided and some are missing, only the missing ones are prompted.
- If the conduit has no inputs (`inputs: {}`), no prompting occurs (unchanged).
- Ctrl+C during prompting aborts cleanly (no traceback).
- Piped/non-TTY stdin skips prompting and lets the engine raise the existing `ValueError` (preserves scriptability).

## Changes

### 1. `app/cli/run.py` — `run_cmd()`

After parsing `inputs_raw` and constructing the `Atelier` instance, but **before** calling `atelier.run_conduit()`:

1. Load the conduit definition: `conduit = atelier.store.read_conduit(conduit_name)`.
2. Compute `missing = [k for k in conduit.inputs if k not in inputs]`.
3. If `missing` is non-empty **and** stdin is a TTY (`sys.stdin.isatty()`):
   - For each key in `missing` (preserving declaration order):
     - Display: `  {name} ({conduit.inputs[name]}): `
     - Read a line from stdin.
     - Add `name: value` to the `inputs` dict.
4. Pass the now-complete `inputs` to `atelier.run_conduit()`.

Use `rich.prompt.Prompt.ask()` or plain `input()` — whichever is simpler. Wrap the prompting loop in a `try/except KeyboardInterrupt` that prints a blank line and calls `raise typer.Exit(code=130)`.

### 2. No other files change

- The engine validation stays as-is (defense in depth).
- `_parse_inputs()` in `_shared.py` is unchanged.
- No new dependencies.

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | `atelier run spec-plan-build` (no `--input`) prompts for `task` with its description | Manual run |
| 2 | `atelier run spec-plan-build -i task="hello"` skips prompting entirely | Manual run |
| 3 | `atelier run spec-plan-build -i task="hello"` with extra unknown inputs still works (engine ignores extras) | Manual run |
| 4 | Partial inputs: `atelier run multiconduit -i a=1` prompts only for missing `b` | Unit test |
| 5 | Conduit with `inputs: {}` runs with no prompting | Unit test |
| 6 | Ctrl+C during prompt exits cleanly with code 130 | Manual run |
| 7 | Non-TTY stdin (piped) skips prompting, engine raises `ValueError` as before | `echo "" \| atelier run spec-plan-build` |
| 8 | Existing tests pass unchanged | `pytest` |

## Out of Scope

- Multiline input values.
- Input validation beyond presence (e.g., type checking, regex).
- Default values for inputs.
- Changes to the WebSocket/API path (`/ws/run` already receives inputs from the frontend).
- Changes to the `tool:hitl` executor (that's task-level prompting, not conduit-level).
