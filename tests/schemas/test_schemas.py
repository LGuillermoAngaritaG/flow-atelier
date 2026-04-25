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


@pytest.mark.parametrize(
    "tool_str",
    ["harness:opencode", "harness:copilot", "harness:cursor"],
)
def test_new_harness_tool_strings_validate(tool_str):
    c = Conduit.model_validate(
        {
            "name": "x",
            "description": "d",
            "tasks": [
                {
                    "t": {
                        "description": "d",
                        "task": "hi",
                        "tool": tool_str,
                        "depends_on": [],
                    }
                }
            ],
        }
    )
    assert c.tasks[0].tool.value == tool_str


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
