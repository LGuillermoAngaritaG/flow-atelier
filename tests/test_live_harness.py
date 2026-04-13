"""Live harness integration tests.

These tests exercise the real ``claude`` and ``codex`` CLIs. They're slow
and cost tokens. If a harness flakes, the test is marked xfail (per the
user's instruction) rather than aborting the suite.
"""
import json
import shutil

import pytest

from app.core.atelier import Atelier


pytestmark = pytest.mark.timeout(300)


def _write_conduit(base, name, body):
    d = base / ".atelier" / "conduits" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "conduit.yaml").write_text(body)


PROMPT = "What is the capital of France? Then write a short four-line poem about it."


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
async def test_claude_noninteractive(workdir):
    _write_conduit(
        workdir,
        "ask_claude",
        f"""
name: ask_claude
description: live claude test
timeout: 240
tasks:
  - ask:
      description: ask claude
      task: "{PROMPT}"
      tool: harness:claude-code
      depends_on: []
""",
    )
    a = Atelier()
    try:
        flow_id = await a.run_conduit("ask_claude", {})
    except Exception as e:
        pytest.xfail(f"live claude flaked: {e}")

    p = a.get_status(flow_id)
    if p.status.value != "completed":
        pytest.xfail(f"claude flow status: {p.status.value}")

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    output = logs[0]["output"].lower()
    assert "paris" in output, f"expected 'paris' in claude output, got: {output[:400]}"


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
async def test_codex_noninteractive(workdir):
    _write_conduit(
        workdir,
        "ask_codex",
        f"""
name: ask_codex
description: live codex test
timeout: 240
tasks:
  - ask:
      description: ask codex
      task: "{PROMPT}"
      tool: harness:codex
      depends_on: []
""",
    )
    a = Atelier()
    try:
        flow_id = await a.run_conduit("ask_codex", {})
    except Exception as e:
        pytest.xfail(f"live codex flaked: {e}")
    p = a.get_status(flow_id)
    if p.status.value != "completed":
        pytest.xfail(f"codex flow status: {p.status.value}")

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    output = logs[0]["output"].lower()
    assert "paris" in output, f"expected 'paris' in codex output, got: {output[:400]}"


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
async def test_claude_interactive_marker(workdir):
    _write_conduit(
        workdir,
        "ask_claude_i",
        f"""
name: ask_claude_i
description: live interactive claude
timeout: 240
tasks:
  - ask:
      description: ask claude interactive
      task: "{PROMPT}"
      tool: harness:claude-code
      depends_on: []
      interactive: true
""",
    )
    a = Atelier()
    try:
        flow_id = await a.run_conduit("ask_claude_i", {})
    except Exception as e:
        pytest.xfail(f"live claude interactive flaked: {e}")

    p = a.get_status(flow_id)
    if p.status.value != "completed":
        pytest.xfail(f"claude interactive flow status: {p.status.value}")

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    output = logs[0]["output"]
    assert "[ATELIER_DONE]" in output
    assert "paris" in output.lower()


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
async def test_codex_interactive_marker(workdir):
    _write_conduit(
        workdir,
        "ask_codex_i",
        f"""
name: ask_codex_i
description: live interactive codex
timeout: 240
tasks:
  - ask:
      description: ask codex interactive
      task: "{PROMPT}"
      tool: harness:codex
      depends_on: []
      interactive: true
""",
    )
    a = Atelier()
    try:
        flow_id = await a.run_conduit("ask_codex_i", {})
    except Exception as e:
        pytest.xfail(f"live codex interactive flaked: {e}")

    p = a.get_status(flow_id)
    if p.status.value != "completed":
        pytest.xfail(f"codex interactive flow status: {p.status.value}")

    logs = json.loads((a.store._flow_dir(flow_id) / "logs.json").read_text())
    output = logs[0]["output"]
    assert "[ATELIER_DONE]" in output
    assert "paris" in output.lower()
