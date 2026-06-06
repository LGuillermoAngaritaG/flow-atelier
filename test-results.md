# Test Results — feature/frontend-dashboard (uncommitted changes)

**Date:** 2026-06-05
**Command:** `python -m pytest tests/ --tb=short`
**Result:** ✅ ALL PASS

## Summary

| Metric   | Count |
|----------|-------|
| Passed   | 497   |
| Failed   | 0     |
| Skipped  | 9     |
| XFailed  | 2     |
| Warnings | 2     |
| **Total**| **508** |

## New Tests Added

### `tests/services/store/test_filesystem_resume.py` (9 tests)
- `test_list_child_flows_empty` — empty list when no children exist
- `test_list_child_flows_returns_children` — returns sorted child flow ids
- `test_list_child_flows_excludes_parent` — parent not included in results
- `test_read_outputs_missing_returns_empty` — empty dict when outputs.yaml absent
- `test_read_outputs_round_trips` — write + read round-trips correctly
- `test_read_outputs_overwrites` — second write overwrites the first
- `test_create_flow_with_explicit_flow_id` — uses provided flow_id
- `test_create_flow_without_flow_id_generates_one` — generates when none provided
- `test_create_flow_with_explicit_flow_id_persists` — directory created with explicit id

### `tests/modules/test_engine_resume.py` (6 tests)
- `test_resume_skips_completed_tasks` — only re-executes the failed task
- `test_resume_reuses_prior_outputs` — downstream tasks see prior completed outputs via templates
- `test_resume_preserves_flow_id` — same flow_id returned
- `test_resume_three_task_pipeline_skips_first` — skips completed tasks in longer pipelines
- `test_resume_fires_on_task_event_only_for_rerun_tasks` — callback only fires for re-executed tasks
- `test_resume_fires_on_task_starting_for_rerun_tasks` — on_task_starting only for re-executed tasks

### `tests/core/test_atelier_resume.py` (5 tests)
- `test_resume_flow_raises_for_non_failed` — ValueError for completed flows
- `test_resume_flow_raises_for_unknown_flow` — FileNotFoundError for missing flow id
- `test_resume_flow_reuses_stored_run_path` — run_path persisted and retrievable
- `test_get_logs_returns_child_entries` — parent logs include child entries
- `test_get_logs_does_not_mutate_entries` — repeated calls return independent objects

### `tests/test_api/test_ws_resume.py` (2 tests)
- `test_ws_resume_emits_started_log_and_complete` — resume on completed flow emits flow_failed
- `test_ws_resume_unknown_flow_emits_flow_failed` — unknown flow id emits flow_failed

### `tests/schemas/test_ws_schemas.py` (4 new tests)
- `test_client_resume_validates` — ResumeMessage validates correctly
- `test_resume_message_dump` — ResumeMessage.model_dump produces expected fields
- `test_server_started_with_parent_fields` — StartedMessage accepts parent fields
- `test_server_started_defaults_parent_fields_to_none` — parent fields default correctly

## Skipped Tests (9, pre-existing)

Pre-existing skips unrelated to this change. No new skips introduced.

## Warnings (2, pre-existing)

Deprecation warnings from `websockets` library — unrelated to this change.
