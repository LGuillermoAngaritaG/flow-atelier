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
    """Verify the sample YAML parses into a Conduit with expected fields."""
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
    """Verify default Conduit and task fields when not provided."""
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
    """Verify duplicate task names cause Conduit validation to fail."""
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
    """Verify new harness tool identifiers validate on Conduit tasks.

    :param tool_str: parametrized tool identifier string under test.
    """
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
    """Verify a task with repeat=0 is rejected by validation."""
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
    """Build a Conduit payload with an `until` task, applying overrides.

    :param overrides: keyword overrides merged into the base task body.
    """
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
    """Verify `until` is accepted when repeat is greater than 1."""
    c = Conduit.model_validate(_task_with_until())
    assert c.tasks[0].until == "output.match(DONE)"


def test_until_not_match_with_repeat_gt_1_ok():
    """Verify `until` with not_match is accepted when repeat > 1."""
    c = Conduit.model_validate(_task_with_until(until="output.not_match(RETRY)"))
    assert c.tasks[0].until == "output.not_match(RETRY)"


def test_until_with_repeat_1_rejected():
    """Verify `until` is rejected when repeat is 1."""
    with pytest.raises(Exception, match="repeat"):
        Conduit.model_validate(_task_with_until(repeat=1))


def test_until_with_invalid_dsl_rejected():
    """Verify invalid DSL in `until` is rejected."""
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_until(until="DONE"))


def test_until_with_invalid_regex_rejected():
    """Verify invalid regex in `until` is rejected."""
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_until(until="output.match([unclosed)"))


def test_task_without_until_still_validates():
    """Verify a task with no `until` and repeat > 1 still validates."""
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
    """Build a Conduit payload with a `while` task, applying overrides.

    :param overrides: keyword overrides merged into the base task body.
    """
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
    """Verify the YAML `while` key populates the `while_` attribute."""
    c = Conduit.model_validate(_task_with_while())
    assert c.tasks[0].while_ == "output.match(retry)"


def test_while_not_match_with_repeat_gt_1_ok():
    """Verify `while` with not_match is accepted when repeat > 1."""
    c = Conduit.model_validate(_task_with_while(**{"while": "output.not_match(ready)"}))
    assert c.tasks[0].while_ == "output.not_match(ready)"


def test_while_with_repeat_1_rejected():
    """Verify `while` is rejected when repeat is 1."""
    with pytest.raises(Exception, match="repeat"):
        Conduit.model_validate(_task_with_while(repeat=1))


def test_while_and_until_mutually_exclusive():
    """Verify `while` and `until` cannot be combined on a single task."""
    body = _task_with_while(until="output.match(DONE)")
    with pytest.raises(Exception) as exc:
        Conduit.model_validate(body)
    msg = str(exc.value)
    assert "until" in msg and "while" in msg


def test_while_with_invalid_dsl_rejected():
    """Verify invalid DSL in `while` is rejected."""
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_while(**{"while": "retry"}))


def test_while_with_invalid_regex_rejected():
    """Verify invalid regex in `while` is rejected."""
    with pytest.raises(Exception):
        Conduit.model_validate(_task_with_while(**{"while": "output.match([unclosed)"}))


def test_while_round_trips_to_yaml_alias():
    """Verify `while_` round-trips back to the `while` YAML alias."""
    c = Conduit.model_validate(_task_with_while())
    dumped = c.tasks[0].model_dump(by_alias=True)
    assert "while" in dumped
    assert dumped["while"] == "output.match(retry)"
    assert "while_" not in dumped


def test_flow_id_roundtrip():
    """Verify a generated flow id parses back into its components."""
    fid = new_flow_id("deploy_pipeline")
    assert FLOW_ID_RE.match(fid)
    conduit, uuid8, ts = parse_flow_id(fid)
    assert conduit == "deploy_pipeline"
    assert len(uuid8) == 8
    assert re.match(r"^\d{8}T\d{6}Z$", ts)


def test_parse_flow_id_rejects_invalid():
    """Verify parse_flow_id raises ValueError for malformed input."""
    with pytest.raises(ValueError):
        parse_flow_id("not-a-flow-id")


def test_progress_roundtrip():
    """Verify Progress serializes to JSON and round-trips faithfully."""
    p = Progress(
        status=FlowStatus.running,
        tasks={"a": TaskProgress(status=TaskStatus.completed, iteration=1, of=1)},
        started_at="2026-04-12T10:00:00Z",
    )
    as_json = p.model_dump_json()
    restored = Progress.model_validate_json(as_json)
    assert restored.tasks["a"].status == TaskStatus.completed
