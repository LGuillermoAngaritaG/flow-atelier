"""End-to-end integration tests (no live harnesses)."""
import builtins
import json

import pytest
import yaml

from app.core.atelier import Atelier


def _write_conduit(base, name, body):
    d = base / ".atelier" / "conduits" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "conduit.yaml").write_text(body)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def test_bash_pipeline_with_conditional_branch(workdir):
    _write_conduit(
        workdir,
        "pipeline",
        """
name: pipeline
description: bash end-to-end
inputs:
  name: who to greet
tasks:
  - hello:
      description: greet
      task: "echo hello {{inputs.name}}"
      tool: tool:bash
      depends_on: []
  - verdict:
      description: emit verdict
      task: "echo 'VERDICT: APPROVE'"
      tool: tool:bash
      depends_on: [hello]
  - deploy:
      description: deploy path
      task: "echo deploying"
      tool: tool:bash
      depends_on:
        - verdict.output.match(APPROVE)
  - rollback:
      description: rollback path
      task: "echo rolling-back"
      tool: tool:bash
      depends_on:
        - verdict.output.not_match(APPROVE)
""",
    )
    a = Atelier()
    flow_id = await a.run_conduit("pipeline", {"name": "world"})
    p = a.get_status(flow_id)
    assert p.status.value == "completed"
    assert p.tasks["deploy"].status.value == "completed"
    assert p.tasks["rollback"].status.value == "skipped"

    logs_path = a.store._flow_dir(flow_id) / "logs.json"
    logs = json.loads(logs_path.read_text())
    hello_log = next(e for e in logs if e["task"] == "hello")
    assert "hello world" in hello_log["output"]


async def test_repeat_creates_multiple_log_entries(workdir):
    _write_conduit(
        workdir,
        "rep",
        """
name: rep
description: repeat
tasks:
  - tick:
      description: tick
      task: "echo tick"
      tool: tool:bash
      depends_on: []
      repeat: 4
""",
    )
    a = Atelier()
    flow_id = await a.run_conduit("rep", {})
    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    ticks = [l for l in logs if l["task"] == "tick"]
    assert len(ticks) == 4
    assert [l["iteration"] for l in ticks] == [1, 2, 3, 4]


async def test_hitl_feeds_downstream_inputs(workdir, monkeypatch):
    _write_conduit(
        workdir,
        "askflow",
        """
name: askflow
description: hitl flow
tasks:
  - ask:
      description: ask human
      task: "Please provide details"
      tool: tool:hitl
      depends_on: []
      inputs:
        username: your name
        confirm: yes/no
  - greet:
      description: greet
      task: "echo '{{inputs.username}} says {{inputs.confirm}}'"
      tool: tool:bash
      depends_on: [ask]
""",
    )
    answers = iter(["alice", "yes"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    a = Atelier()
    flow_id = await a.run_conduit("askflow", {})
    p = a.get_status(flow_id)
    assert p.status.value == "completed"

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    greet_log = next(l for l in logs if l["task"] == "greet")
    assert "alice says yes" in greet_log["output"]

    input_yaml = yaml.safe_load(
        (a.store._flow_dir(flow_id) / "input.yaml").read_text()
    )
    assert input_yaml["username"] == "alice"
    assert input_yaml["confirm"] == "yes"


async def test_nested_conduit(workdir):
    _write_conduit(
        workdir,
        "child",
        """
name: child
description: nested child
inputs:
  label: label
tasks:
  - step:
      description: step
      task: "echo child-{{inputs.label}}"
      tool: tool:bash
      depends_on: []
""",
    )
    _write_conduit(
        workdir,
        "parent",
        """
name: parent
description: calls child
tasks:
  - setup:
      description: setup
      task: "echo setup-done"
      tool: tool:bash
      depends_on: []
  - nested:
      description: run child
      task: child
      tool: tool:conduit
      depends_on: [setup]
      inputs:
        label: "{{setup.output}}"
""",
    )
    a = Atelier()
    flow_id = await a.run_conduit("parent", {})
    p = a.get_status(flow_id)
    assert p.status.value == "completed"
    parent_dir = a.store._flow_dir(flow_id)
    child_flows = list((parent_dir / "flows").iterdir())
    assert len(child_flows) == 1
    child_dir = child_flows[0]
    child_logs = json.loads((child_dir / "logs.json").read_text())
    assert any("child-setup-done" in e["output"] for e in child_logs)


async def test_fail_fast_flow_failed_status(workdir):
    _write_conduit(
        workdir,
        "fast",
        """
name: fast
description: ff
tasks:
  - bad:
      description: fails
      task: "exit 1"
      tool: tool:bash
      depends_on: []
  - good:
      description: good
      task: "echo hi"
      tool: tool:bash
      depends_on: []
""",
    )
    a = Atelier()
    with pytest.raises(RuntimeError):
        await a.run_conduit("fast", {})
    flow_id = a.list_flows("fast")[0]
    p = a.get_status(flow_id)
    assert p.status.value == "failed"
    assert p.tasks["bad"].status.value == "failed"


async def test_until_early_exit_with_real_bash(workdir):
    _write_conduit(
        workdir,
        "poller",
        """
name: poller
description: poll with early exit
tasks:
  - poll:
      description: echo HIT on the 3rd call
      task: "echo x >> counter.log; n=$(wc -l < counter.log | tr -d ' '); if [ \\"$n\\" -ge 3 ]; then echo HIT; else echo wait; fi"
      tool: tool:bash
      depends_on: []
      repeat: 5
      until: "output.match(HIT)"
""",
    )
    a = Atelier()
    flow_id = await a.run_conduit("poller", {})
    p = a.get_status(flow_id)
    assert p.status.value == "completed"
    assert p.tasks["poll"].status.value == "completed"
    assert p.tasks["poll"].iteration == 3
    assert p.tasks["poll"].of == 5

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    poll_logs = [l for l in logs if l["task"] == "poll"]
    assert len(poll_logs) == 3
    assert "HIT" in poll_logs[-1]["output"]


async def test_concurrency_cap_honored(workdir):
    # four sleeps with cap 2 should take >= 2 * sleep
    _write_conduit(
        workdir,
        "par",
        """
name: par
description: cap
max_concurrency: 2
tasks:
  - a:
      description: a
      task: "sleep 0.3"
      tool: tool:bash
      depends_on: []
  - b:
      description: b
      task: "sleep 0.3"
      tool: tool:bash
      depends_on: []
  - c:
      description: c
      task: "sleep 0.3"
      tool: tool:bash
      depends_on: []
  - d:
      description: d
      task: "sleep 0.3"
      tool: tool:bash
      depends_on: []
""",
    )
    import time
    a = Atelier()
    t0 = time.monotonic()
    await a.run_conduit("par", {})
    elapsed = time.monotonic() - t0
    # With cap=2 and 4 tasks at 0.3s each, expected ≥ 0.6s
    assert elapsed >= 0.55
