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
    # New table includes the source tag and column headers.
    assert "project" in result.output
    assert "name" in result.output
    assert "tasks" in result.output
    assert "inputs" in result.output


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
    assert "deploy" in out and "global" in out
    assert "hello" in out and "project" in out
    # hello only appears once (shadowed, not duplicated). Match by row,
    # i.e. lines containing the conduit name in the first column.
    name_col_lines = [
        l for l in out.splitlines()
        if l.startswith("│") and "hello" in l.split("│")[1]
    ]
    assert len(name_col_lines) == 1


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
    # New table-based output includes per-flow status and conduit columns.
    assert "status" in result.output
    assert "completed" in result.output
    assert "duration" in result.output


def test_status_includes_duration_and_summary(workdir):
    runner = CliRunner()
    run_result = runner.invoke(app, ["run", "hello", "--input", "name=a"])
    line = [l for l in run_result.output.splitlines() if "flow_id" in l][0]
    flow_id = line.split()[-1]
    result = runner.invoke(app, ["status", flow_id])
    assert result.exit_code == 0
    assert "started=" in result.output
    assert "duration=" in result.output
    # Aggregate summary uses ✓ glyph for the completed task.
    assert "✓" in result.output


def test_run_prints_summary_footer(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["run", "hello", "--input", "name=a"])
    assert result.exit_code == 0, result.output
    # Footer line: glyph(s) + total duration.
    assert "✓1" in result.output
    assert "total" in result.output


# ---------------------------------------------------------------- logs cmd


MULTI_CONDUIT_YAML = """
name: multi
description: multi-task
tasks:
  - alpha:
      description: a
      task: "echo alpha-output; echo alpha-err >&2"
      tool: tool:bash
      depends_on: []
  - beta:
      description: b
      task: "echo beta-output"
      tool: tool:bash
      depends_on: [alpha]
"""


def _write_multi(workdir):
    d = workdir / ".atelier" / "conduits" / "multi"
    d.mkdir(parents=True)
    (d / "conduit.yaml").write_text(MULTI_CONDUIT_YAML)


def _run_and_id(runner, conduit, *args):
    res = runner.invoke(app, ["run", conduit, *args])
    line = [l for l in res.output.splitlines() if "flow_id" in l][0]
    return line.split()[-1]


def test_logs_unknown_flow(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "no_such_flow"])
    assert result.exit_code != 0
    assert "unknown flow" in result.output


def test_logs_shows_task_output(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "alpha-output" in result.output
    assert "beta-output" in result.output


def test_logs_filter_by_task(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id, "--task", "alpha"])
    assert result.exit_code == 0, result.output
    assert "alpha-output" in result.output
    assert "beta-output" not in result.output


def test_logs_show_stderr(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id, "--task", "alpha", "--show", "stderr"])
    assert result.exit_code == 0, result.output
    assert "alpha-err" in result.output
    # stdout body should be omitted in stderr-only mode.
    assert "alpha-output" not in result.output


def test_logs_unknown_task_filter(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id, "--task", "ghost"])
    assert result.exit_code != 0
    assert "no log entries" in result.output


# ---------------------------------------------------------------- prefix match


def test_status_accepts_short_prefix(workdir):
    """git-style: a unique short prefix should resolve to the full flow id."""
    runner = CliRunner()
    flow_id = _run_and_id(runner, "hello", "--input", "name=a")
    short = flow_id[: len(flow_id.split("_")[0]) + 5]  # conduit + 4 hex chars
    result = runner.invoke(app, ["status", short])
    assert result.exit_code == 0, result.output
    assert "completed" in result.output


def test_logs_accepts_short_prefix(workdir):
    runner = CliRunner()
    flow_id = _run_and_id(runner, "hello", "--input", "name=a")
    short = flow_id[: len(flow_id.split("_")[0]) + 5]
    result = runner.invoke(app, ["logs", short])
    assert result.exit_code == 0, result.output
    assert "greet" in result.output


def test_status_ambiguous_prefix(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    # Two flows from the same conduit → "multi_" is ambiguous.
    _run_and_id(runner, "multi")
    _run_and_id(runner, "multi")
    result = runner.invoke(app, ["status", "multi_"])
    assert result.exit_code != 0
    assert "ambiguous" in result.output.lower()


def test_status_prefix_no_match(workdir):
    runner = CliRunner()
    _run_and_id(runner, "hello", "--input", "name=a")
    result = runner.invoke(app, ["status", "nope_"])
    assert result.exit_code != 0
    assert "unknown flow" in result.output


# ---------------------------------------------------------------- --json mode


import json as _json


def test_list_flows_json(workdir):
    runner = CliRunner()
    _run_and_id(runner, "hello", "--input", "name=a")
    result = runner.invoke(app, ["list", "flows", "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    entry = data[0]
    for key in ("flow_id", "conduit", "status", "started_at", "finished_at",
                "duration_seconds", "task_counts"):
        assert key in entry
    assert entry["conduit"] == "hello"
    assert entry["status"] == "completed"
    assert entry["task_counts"]["completed"] == 1


def test_list_conduits_json(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["list", "conduits", "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert isinstance(data, list)
    by_name = {e["name"]: e for e in data}
    assert "hello" in by_name
    assert by_name["hello"]["source"] == "project"
    assert by_name["hello"]["tasks"] == 1


def test_status_json(workdir):
    runner = CliRunner()
    flow_id = _run_and_id(runner, "hello", "--input", "name=a")
    result = runner.invoke(app, ["status", flow_id, "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["flow_id"] == flow_id
    assert data["status"] == "completed"
    assert "tasks" in data and "greet" in data["tasks"]
    assert data["tasks"]["greet"]["status"] == "completed"


def test_logs_json(workdir):
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id, "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert isinstance(data, list)
    tasks = [e["task"] for e in data]
    assert "alpha" in tasks and "beta" in tasks
    alpha = next(e for e in data if e["task"] == "alpha")
    assert "alpha-output" in alpha["output"]


# ---------------------------------------------------------------- --follow


def test_logs_follow_on_completed_flow_exits(workdir):
    """--follow on an already-terminal flow must print all entries and exit
    on the first poll iteration (status != running)."""
    _write_multi(workdir)
    runner = CliRunner()
    flow_id = _run_and_id(runner, "multi")
    result = runner.invoke(app, ["logs", flow_id, "--follow"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_logs_follow_unknown_flow(workdir):
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "no_such_flow", "--follow"])
    assert result.exit_code != 0
    assert "unknown flow" in result.output


def test_run_missing_input_fails(workdir):
    runner = CliRunner()
    # conduit has no declared inputs but the task uses {{inputs.name}} — engine
    # does not enforce that unused-declared inputs match, so this command
    # will fail only because the template references a missing input.
    result = runner.invoke(app, ["run", "hello"])
    assert result.exit_code != 0


FAILING_CONDUIT_YAML = """
name: failing
description: Always fails
tasks:
  - boom:
      description: fail on purpose
      task: "echo bye; exit 9"
      tool: tool:bash
      depends_on: []
"""


def test_run_failure_prints_flow_id_and_status_hint(tmp_path, monkeypatch):
    """Failure output must include the flow_id and a next-step hint so
    the user can inspect what happened. Previously the flow_id was only
    printed on success, leaving failed runs un-inspectable.
    """
    atelier_dir = tmp_path / ".atelier"
    (atelier_dir / "conduits" / "failing").mkdir(parents=True)
    (atelier_dir / "conduits" / "failing" / "conduit.yaml").write_text(
        FAILING_CONDUIT_YAML
    )
    monkeypatch.chdir(tmp_path)
    for k in list(os.environ):
        if k.startswith("ATELIER_") and k != "ATELIER_GLOBAL_ATELIER_DIR":
            monkeypatch.delenv(k, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["run", "failing"])
    assert result.exit_code != 0, result.output
    assert "flow_id" in result.output
    # Hint should point the user at how to investigate.
    assert "atelier status" in result.output
    # The id should match the failing_<...> shape.
    assert "failing_" in result.output


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


def test_render_failed_task_shows_both_stdout_and_stderr():
    """When a failure has both stdout and stderr, the panel must show
    both — stderr is the most important diagnostic and was previously
    hidden by `body_source = event.output or event.stderr`.
    """
    event = TaskEvent(
        task="boom",
        tool="tool:bash",
        exit_code=7,
        duration_seconds=0.01,
        output="about to fail on stdout",
        stdout="about to fail on stdout",
        stderr="this is the actual error",
        success=False,
    )
    out = _capture(event)
    assert "about to fail on stdout" in out
    assert "this is the actual error" in out
    # Section labels make the split unambiguous to a human reader.
    assert "stdout" in out.lower()
    assert "stderr" in out.lower()


def test_render_failed_task_with_only_output_does_not_label_sections():
    """When only stdout/output is present (no stderr), keep the
    existing single-body rendering — don't gratuitously add labels.
    """
    event = TaskEvent(
        task="boom",
        tool="tool:bash",
        exit_code=2,
        duration_seconds=0.02,
        output="just some output",
        stdout="just some output",
        stderr="",
        success=False,
    )
    out = _capture(event)
    assert "just some output" in out
    # No "stderr:" label since there's nothing to label.
    assert "stderr:" not in out.lower()


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


def test_render_live_streamed_task_is_compact():
    """Interactive harness tasks already streamed their full transcript;
    the after-the-fact panel should be a one-line summary, not a body.
    """
    event = TaskEvent(
        task="ask_then_answer",
        tool="harness:claude-code",
        exit_code=0,
        duration_seconds=12.5,
        output="long multi-turn transcript that already streamed",
        success=True,
        live_streamed=True,
    )
    out = _capture(event)
    assert "ask_then_answer" in out
    assert "harness:claude-code" in out
    assert "streamed live above" in out
    # No box-drawing — compact line, not a panel.
    assert "─" not in out
    # Body content must NOT be re-rendered.
    assert "long multi-turn transcript" not in out


def test_render_skipped_task_shows_reason():
    from app.schemas.progress import TaskStatus
    event = TaskEvent(
        task="deploy",
        tool="tool:bash",
        success=False,
        status=TaskStatus.skipped,
        reason="condition not met: review.output.match(APPROVE)",
    )
    out = _capture(event)
    # One-line summary, not a panel.
    assert "deploy" in out
    assert "skipped" in out.lower()
    assert "condition not met" in out
    # No box-drawing characters — must be a compact line.
    assert "─" not in out


def test_render_cancelled_task_shows_reason():
    from app.schemas.progress import TaskStatus
    event = TaskEvent(
        task="after",
        tool="tool:bash",
        success=False,
        status=TaskStatus.cancelled,
        reason="upstream failed",
    )
    out = _capture(event)
    assert "after" in out
    assert "cancelled" in out.lower()
    assert "upstream failed" in out
    assert "─" not in out


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
