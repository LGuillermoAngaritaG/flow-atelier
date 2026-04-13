"""CLI smoke tests via Typer's CliRunner."""
import io
import os

import pytest
from rich.console import Console
from typer.testing import CliRunner

from app.main import _render_task_event, _truncate_tail, app
from app.schemas.log import TaskEvent

CONDUIT_YAML = """
name: hello
description: Say hello
tasks:
  - greet:
      description: greet
      task: "echo hello {{inputs.name}}"
      tool: tool:bash
      depends_on: []
"""


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    atelier_dir = tmp_path / ".atelier"
    (atelier_dir / "conduits" / "hello").mkdir(parents=True)
    (atelier_dir / "conduits" / "hello" / "conduit.yaml").write_text(CONDUIT_YAML)
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_") and k != "ATELIER_GLOBAL_ATELIER_DIR":
            monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_list_conduits(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["list", "conduits"])
    assert result.exit_code == 0, result.output
    assert "hello" in result.output
    assert "[project]" in result.output


GLOBAL_DEPLOY_YAML = """
name: deploy
description: Global deploy
tasks:
  - step:
      description: step
      task: "echo deploying"
      tool: tool:bash
      depends_on: []
"""


def test_list_conduits_shows_global_and_shadowing(
    workdir, _isolate_global_atelier_dir
):
    global_dir = _isolate_global_atelier_dir
    (global_dir / "conduits" / "deploy").mkdir(parents=True)
    (global_dir / "conduits" / "deploy" / "conduit.yaml").write_text(
        GLOBAL_DEPLOY_YAML
    )
    # a global "hello" that should be shadowed by the project copy from workdir
    (global_dir / "conduits" / "hello").mkdir(parents=True)
    (global_dir / "conduits" / "hello" / "conduit.yaml").write_text(
        GLOBAL_DEPLOY_YAML.replace("deploy", "hello")
    )

    runner = CliRunner()
    result = runner.invoke(app, ["list", "conduits"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "deploy" in out and "[global]" in out
    assert "hello" in out and "[project]" in out
    # hello only appears once (shadowed, not duplicated)
    hello_lines = [l for l in out.splitlines() if "hello" in l]
    assert len(hello_lines) == 1


def test_run_and_status(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["run", "hello", "--input", "name=world"])
    assert result.exit_code == 0, result.output
    assert "flow_id" in result.output
    # Live output is on by default: the greet task should show up.
    assert "greet" in result.output
    assert "tool:bash" in result.output
    # extract flow id
    line = [l for l in result.output.splitlines() if "flow_id" in l][0]
    flow_id = line.split()[-1]
    result2 = runner.invoke(app, ["status", flow_id])
    assert result2.exit_code == 0
    assert "greet" in result2.output
    assert "completed" in result2.output


def test_list_flows(workdir):
    runner = CliRunner()
    runner.invoke(app, ["run", "hello", "--input", "name=a"])
    result = runner.invoke(app, ["list", "flows"])
    assert result.exit_code == 0
    assert "hello_" in result.output


def test_run_missing_input_fails(workdir):
    runner = CliRunner()
    # conduit has no declared inputs but the task uses {{inputs.name}} — engine
    # does not enforce that unused-declared inputs match, so this command
    # will fail only because the template references a missing input.
    result = runner.invoke(app, ["run", "hello"])
    assert result.exit_code != 0


# ---------------------------------------------------------------- renderer


def _capture(event: TaskEvent) -> str:
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, color_system=None, width=120
    )
    _render_task_event(event, console)
    return buf.getvalue()


def test_truncate_tail_short_passthrough():
    text = "line1\nline2\nline3"
    out, dropped = _truncate_tail(text, max_lines=20)
    assert out == text
    assert dropped == 0


def test_truncate_tail_exactly_max():
    text = "\n".join(f"l{i}" for i in range(20))
    out, dropped = _truncate_tail(text, max_lines=20)
    assert dropped == 0
    assert out == text


def test_truncate_tail_drops_head():
    text = "\n".join(f"l{i}" for i in range(100))
    out, dropped = _truncate_tail(text, max_lines=20)
    assert dropped == 80
    # Only the last 20 kept.
    assert out.splitlines() == [f"l{i}" for i in range(80, 100)]


def test_truncate_tail_empty():
    assert _truncate_tail("", max_lines=20) == ("", 0)


def test_render_successful_task_with_output():
    event = TaskEvent(
        task="greet",
        tool="tool:bash",
        exit_code=0,
        duration_seconds=0.12,
        output="hello world",
        stdout="hello world",
        success=True,
    )
    out = _capture(event)
    assert "greet" in out
    assert "tool:bash" in out
    assert "hello world" in out
    assert "exit=0" in out
    assert "0.12s" in out


def test_render_successful_task_empty_output_is_compact():
    event = TaskEvent(
        task="ping",
        tool="tool:bash",
        exit_code=0,
        duration_seconds=0.01,
        output="",
        stdout="",
        success=True,
    )
    out = _capture(event)
    assert "ping" in out
    assert "no output" in out
    # No panel border glyph for the compact path.
    assert "─" not in out


def test_render_failed_task_falls_back_to_stderr():
    event = TaskEvent(
        task="boom",
        tool="tool:bash",
        exit_code=1,
        duration_seconds=0.05,
        output="",
        stdout="",
        stderr="segfault",
        success=False,
    )
    out = _capture(event)
    assert "boom" in out
    assert "segfault" in out
    assert "exit=1" in out


def test_render_truncates_long_output():
    long_out = "\n".join(f"line{i}" for i in range(100))
    event = TaskEvent(
        task="chatty",
        tool="harness:claude-code",
        exit_code=0,
        duration_seconds=1.5,
        output=long_out,
        success=True,
    )
    out = _capture(event)
    assert "80 lines truncated" in out
    # First line of original data should be gone; tail lines present.
    assert "line0\n" not in out
    assert "line99" in out


def test_render_iteration_shown_when_repeat_gt_one():
    event = TaskEvent(
        task="retry",
        tool="tool:bash",
        iteration=2,
        of=3,
        exit_code=0,
        duration_seconds=0.1,
        output="ok",
        success=True,
    )
    out = _capture(event)
    assert "(2/3)" in out
