"""Schema unit tests."""
import re

import pytest
import yaml

from app.schemas.conduit import Conduit, ToolType
from app.schemas.flow import new_flow_id, parse_flow_id, FLOW_ID_RE
from app.schemas.progress import FlowStatus, Progress, TaskProgress, TaskStatus


SAMPLE_YAML = """
name: deploy_pipeline
description: Build test deploy
timeout: 600
max_concurrency: 4
inputs:
  repo_url: repo URL
  branch: branch name
tasks:
  - clone_repo:
      description: Clone
      task: "git clone {{inputs.repo_url}}"
      tool: tool:bash
      depends_on: []
  - run_tests:
      description: Test
      task: "make test"
      tool: tool:bash
      depends_on: [clone_repo]
      repeat: 3
  - review:
      description: Review
      task: "review the code"
      tool: harness:claude-code
      depends_on: [clone_repo]
      interactive: false
  - deploy:
      description: Deploy
      task: "make deploy"
      tool: tool:bash
      depends_on:
        - run_tests
        - review.output.match(VERDICT:\\s*APPROVE)
  - approve:
      description: human gate
      task: "Please answer"
      tool: tool:hitl
      depends_on: [run_tests]
      inputs:
        confirm: "Type yes to confirm"
"""


def test_parse_sample_conduit():
    data = yaml.safe_load(SAMPLE_YAML)
    conduit = Conduit.model_validate(data)
    assert conduit.name == "deploy_pipeline"
    assert conduit.timeout == 600
    assert conduit.max_concurrency == 4
    assert len(conduit.tasks) == 5
    names = [t.name for t in conduit.tasks]
    assert names == ["clone_repo", "run_tests", "review", "deploy", "approve"]
    run_tests = conduit.tasks[1]
    assert run_tests.repeat == 3
    assert run_tests.tool == ToolType.bash
    review = conduit.tasks[2]
    assert review.tool == ToolType.claude
    deploy = conduit.tasks[3]
    assert "review.output.match(VERDICT:\\s*APPROVE)" in deploy.depends_on
    approve = conduit.tasks[4]
    assert approve.inputs == {"confirm": "Type yes to confirm"}


def test_defaults():
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "tasks": [
                {"t": {"description": "d", "task": "echo hi", "tool": "tool:bash", "depends_on": []}}
            ],
        }
    )
    assert c.timeout == 3600
    assert c.max_concurrency == 3
    assert c.tasks[0].repeat == 1
    assert c.tasks[0].interactive is False


def test_duplicate_task_names_rejected():
    with pytest.raises(Exception):
        Conduit.model_validate(
            {
                "name": "x",
                "description": "d",
                "tasks": [
                    {"a": {"description": "d", "task": "echo 1", "tool": "tool:bash", "depends_on": []}},
                    {"a": {"description": "d", "task": "echo 2", "tool": "tool:bash", "depends_on": []}},
                ],
            }
        )


def test_repeat_must_be_positive():
    with pytest.raises(Exception):
        Conduit.model_validate(
            {
                "name": "x",
                "description": "d",
                "tasks": [
                    {"a": {"description": "d", "task": "x", "tool": "tool:bash", "depends_on": [], "repeat": 0}}
                ],
            }
        )


def _task_with_until(**overrides):
    base = {
        "description": "d",
        "task": "x",
        "tool": "tool:bash",
        "depends_on": [],
        "repeat": 3,
        "until": "output.match(DONE)",
    }
    base.update(overrides)
    return {
        "name": "x",
        "description": "d",
        "tasks": [{"a": base}],
    }


def test_until_with_repeat_gt_1_ok():
    c = Conduit.model_validate(_task_with_until())
    assert c.tasks[0].until == "output.match(DONE)"


def test_until_not_match_with_repeat_gt_1_ok():
    c = Conduit.model_validate(_task_with_until(until="output.not_match(RETRY)"))
    assert c.tasks[0].until == "output.not_match(RETRY)"


def test_until_with_repeat_1_rejected():
    with pytest.raises(Exception, match="repeat"):
        Conduit.model_validate(_task_with_until(repeat=1))


def test_until_with_invalid_dsl_rejected():
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_until(until="DONE"))


def test_until_with_invalid_regex_rejected():
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_until(until="output.match([unclosed)"))


def test_task_without_until_still_validates():
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "tasks": [
                {"a": {"description": "d", "task": "x", "tool": "tool:bash",
                       "depends_on": [], "repeat": 2}}
            ],
        }
    )
    assert c.tasks[0].until is None


# ------------------------------------------------------------------ while


def _task_with_while(**overrides):
    base = {
        "description": "d",
        "task": "x",
        "tool": "tool:bash",
        "depends_on": [],
        "repeat": 3,
        "while": "output.match(retry)",
    }
    base.update(overrides)
    return {
        "name": "x",
        "description": "d",
        "tasks": [{"a": base}],
    }


def test_while_yaml_key_loads_into_while_attr():
    c = Conduit.model_validate(_task_with_while())
    assert c.tasks[0].while_ == "output.match(retry)"


def test_while_not_match_with_repeat_gt_1_ok():
    c = Conduit.model_validate(_task_with_while(**{"while": "output.not_match(ready)"}))
    assert c.tasks[0].while_ == "output.not_match(ready)"


def test_while_with_repeat_1_rejected():
    with pytest.raises(Exception, match="repeat"):
        Conduit.model_validate(_task_with_while(repeat=1))


def test_while_and_until_mutually_exclusive():
    body = _task_with_while(until="output.match(DONE)")
    with pytest.raises(Exception) as exc:
        Conduit.model_validate(body)
    msg = str(exc.value)
    assert "until" in msg and "while" in msg


def test_while_with_invalid_dsl_rejected():
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_while(**{"while": "retry"}))


def test_while_with_invalid_regex_rejected():
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_while(**{"while": "output.match([unclosed)"}))


def test_while_round_trips_to_yaml_alias():
    c = Conduit.model_validate(_task_with_while())
    dumped = c.tasks[0].model_dump(by_alias=True)
    assert "while" in dumped
    assert dumped["while"] == "output.match(retry)"
    assert "while_" not in dumped


def test_flow_id_roundtrip():
    fid = new_flow_id("deploy_pipeline")
    assert FLOW_ID_RE.match(fid)
    conduit, uuid8, ts = parse_flow_id(fid)
    assert conduit == "deploy_pipeline"
    assert len(uuid8) == 8
    assert re.match(r"^\d{8}T\d{6}Z$", ts)


def test_parse_flow_id_rejects_invalid():
    with pytest.raises(ValueError):
        parse_flow_id("not-a-flow-id")


def test_progress_roundtrip():
    p = Progress(
        status=FlowStatus.running,
        tasks={"a": TaskProgress(status=TaskStatus.completed, iteration=1, of=1)},
        started_at="2026-04-12T10:00:00Z",
    )
    as_json = p.model_dump_json()
    restored = Progress.model_validate_json(as_json)
    assert restored.tasks["a"].status == TaskStatus.completed
