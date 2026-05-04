# Todo: Multi-line terminal input with prompt_toolkit

- [x] **Task 1**: Add `prompt-toolkit>=3.0` to `pyproject.toml` dependencies → verify: `uv sync && python -c "import prompt_toolkit"`
- [x] **Task 2**: Create `app/cli/multiline_input.py` with `multiline_input()` async + `multiline_input_sync()` → verify: unit tests (Task 5)
- [x] **Task 3a**: Wire into `TerminalPromptSink.request_input` (TTY branch) → verify: `pytest tests/services/executor/test_prompt_sink.py`
- [x] **Task 3b**: Wire into `HitlExecutor.execute` → verify: `pytest tests/services/executor/test_hitl.py`
- [x] **Task 3c**: Wire into `run.py` missing-conduit-input prompt → verify: `pytest tests/ -v`
- [x] **Task 4**: Fix existing tests broken by the monkeypatch changes → verify: `pytest tests/ -v`
- [x] **Task 5**: Add `tests/cli/test_multiline_input.py` (non-TTY fallback, TTY path, hint, sync variant) → verify: `pytest tests/cli/test_multiline_input.py -v`
- [x] **Checkpoint**: Full test suite green → verify: `pytest tests/ -v` (439 passed, 2 pre-existing live harness failures)
- [ ] **Task 6**: Manual verification on TTY (human)
