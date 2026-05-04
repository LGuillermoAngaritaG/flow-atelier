# Plan: Multi-line terminal input with prompt_toolkit

## Summary

Replace `builtins.input()` at three terminal input sites with `prompt_toolkit` multi-line sessions. Enter inserts a newline; Alt+Enter submits. Piped stdin remains single-line.

## Dependency graph

```
pyproject.toml (add prompt-toolkit)
        │
        ▼
app/cli/multiline_input.py (new shared helper)
        │
        ├──▶ prompt_sink.py (site 1: TerminalPromptSink.request_input)
        ├──▶ hitl.py         (site 2: HitlExecutor.execute)
        └──▶ run.py           (site 3: CLI missing-conduit-input prompt)
```

All three call sites depend on the shared helper. No dependencies between the sites themselves.

---

## Tasks

### Task 1: Add `prompt-toolkit` dependency

**Files:** `pyproject.toml`

**Changes:**
- Add `"prompt-toolkit>=3.0"` to `[project.dependencies]`

**Acceptance criteria:**
- `uv pip install -e .` succeeds
- `python -c "import prompt_toolkit"` exits 0

**Verify:** `uv sync && python -c "import prompt_toolkit; print(prompt_toolkit.__version__)"`

---

### Task 2: Create `app/cli/multiline_input.py`

**Files:** `app/cli/multiline_input.py` (new)

**Changes:**
- Implement `async def multiline_input(prompt, hint) -> str`
  - TTY path: print dim hint, run `prompt_toolkit.PromptSession(multiline=True).prompt()` via `asyncio.to_thread()`
  - Non-TTY path: delegate to `builtins.input(prompt)`
- Custom key bindings: Alt+Enter (Escape, Enter) accepts buffer (prompt_toolkit default Enter inserts newline in multiline mode)
- Decide sync vs async for the run.py call site: since run.py calls `asyncio.run()` later and the missing-input prompt is in sync code before that, add a thin `multiline_input_sync()` wrapper that calls prompt_toolkit directly (it's sync under the hood) — avoids a second `asyncio.run()`

**Acceptance criteria:**
- Unit test: non-TTY fallback returns `builtins.input()` result
- Unit test: TTY path calls prompt_toolkit (monkeypatched)
- Function signature matches spec: `async def multiline_input(prompt: str = "› ", hint: str = "") -> str`

**Verify:** `pytest tests/cli/test_multiline_input.py -v` (will be created in Task 5)

---

### Task 3: Wire `multiline_input` into the three call sites

**Files:** `app/services/executor/prompt_sink.py`, `app/services/executor/hitl.py`, `app/cli/run.py`

**Changes per site:**

**3a. `TerminalPromptSink.request_input`** (`prompt_sink.py:139-140`)
- Replace TTY branch `await asyncio.to_thread(builtins.input, "› ")` with `await multiline_input("› ", hint="Alt+Enter to submit")`
- Non-TTY branch (line 142-143) unchanged

**3b. `HitlExecutor.execute`** (`hitl.py:50`)
- Replace `await asyncio.to_thread(builtins.input, prompt)` with `await multiline_input(prompt, hint="Alt+Enter to submit")`
- Non-TTY echo logic (line 54-55) unchanged

**3c. `run.py` missing-conduit-input prompt** (`run.py:44`)
- Replace `input(f"  {key} ({conduit.inputs[key]}): ")` with `multiline_input_sync(f"  {key} ({conduit.inputs[key]}): ", hint="Alt+Enter to submit")`
- This is sync code (before `asyncio.run`), so use the sync variant

**Acceptance criteria:**
- Each site imports from `app.cli.multiline_input`
- Unused `builtins` import removed from hitl.py if no longer needed
- The `builtins` import in prompt_sink.py may still be needed for the non-TTY branch — check and keep if so
- Existing tests still pass (they monkeypatch `builtins.input` or `request_input` directly)

**Verify:** `pytest tests/ -v --timeout=30`

---

### Task 4: Fix existing tests broken by the change

**Files:** `tests/services/executor/test_hitl.py`, `tests/services/executor/test_prompt_sink.py`

**Changes:**
- Existing hitl tests monkeypatch `builtins.input`. After Task 3, `HitlExecutor` calls `multiline_input` instead. These tests need to monkeypatch `app.services.executor.hitl.multiline_input` (or `app.cli.multiline_input.multiline_input`).
- Existing prompt_sink tests monkeypatch `builtins.input`. The TTY-path tests need to monkeypatch `multiline_input` instead. The non-TTY tests may still work (since `multiline_input` delegates to `builtins.input` on non-TTY), but the TTY tests mock `builtins.input` directly — those need updating.
- Harness tests (`test_harness.py`) use `RecordingSink` which mocks `request_input` entirely — these should be unaffected.

**Acceptance criteria:**
- All existing tests pass
- No test regressions

**Verify:** `pytest tests/ -v`

---

### Task 5: Add new unit tests for `multiline_input`

**Files:** `tests/cli/test_multiline_input.py` (new)

**Tests to write:**
1. **Non-TTY fallback**: monkeypatch `sys.stdin.isatty()` → `False`, monkeypatch `builtins.input` → canned string. Assert returns that string.
2. **TTY path calls prompt_toolkit**: monkeypatch `sys.stdin.isatty()` → `True`, monkeypatch `PromptSession.prompt` → canned string. Assert returns that string.
3. **Hint printed on TTY**: verify the hint text is printed (capture stdout or monkeypatch print).
4. **Sync variant works**: test `multiline_input_sync` non-TTY fallback.

**Acceptance criteria:**
- All 4 tests pass
- Tests don't require a real TTY

**Verify:** `pytest tests/cli/test_multiline_input.py -v`

---

### Checkpoint: Full test suite green

**Verify:** `pytest tests/ -v`

---

### Task 6: Manual verification (human)

- Run `atelier run <interactive-conduit>` on a TTY
  - Confirm `(Alt+Enter to submit)` hint appears
  - Confirm Enter inserts newline
  - Confirm Alt+Enter submits
  - Confirm multi-line text reaches the agent
- Pipe test: `echo "hello" | atelier run <conduit>` — single-line behavior unchanged

---

## Boundaries (from spec)

**Always:** Fall back to `builtins.input()` when stdin is not a TTY. Show Alt+Enter hint every time. Preserve `EOFError`/`KeyboardInterrupt` handling.

**Never:** Change WebSocket-based input. Change `PromptSink` protocol interface. Add `prompt_toolkit` to piped-stdin path.

**Ask first:** If Alt+Enter binding conflicts with a terminal emulator default.

## Key decisions

1. **Sync wrapper for run.py**: The missing-input prompt in `run.py` runs before `asyncio.run()`. Rather than nesting a second `asyncio.run()`, provide `multiline_input_sync()` that calls prompt_toolkit directly (it's sync under the hood). This is the simpler path per spec guidance.

2. **Test strategy**: Existing tests that monkeypatch `builtins.input` will break for the TTY path. Fix by monkeypatching `multiline_input` at the import site instead. Non-TTY tests may survive since `multiline_input` delegates to `builtins.input`, but verify.
