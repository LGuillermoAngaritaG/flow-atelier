"""CLI tests for ``atelier ask``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from click import unstyle
from typer.testing import CliRunner

from flow_atelier.cli import app

FAKE_AGENT = Path(__file__).resolve().parents[1] / "fixtures" / "fake_acp_agent.py"


def test_ask_runs_an_interactive_claude_session_in_path(tmp_path, monkeypatch) -> None:
    """The query and path reach one interactive Claude task end to end.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    script = json.dumps(
        {
            "turns": [
                {"chunks": ["Which colour? "], "stop": "end_turn"},
                {"chunks": ["Blue it is. [ATELIER_DONE]"], "stop": "end_turn"},
            ]
        }
    )
    monkeypatch.setenv(
        "ATELIER_CLAUDE_LAUNCH_CMD",
        json.dumps([sys.executable, str(FAKE_AGENT), "--script", script]),
    )

    query = "Help me write a specification"
    result = CliRunner().invoke(
        app,
        ["ask", query, "--path", str(project)],
        input="blue\n",
    )

    assert result.exit_code == 0, result.output
    assert "Which colour?" in result.output
    assert "Blue it is." in result.output
    assert "[ATELIER_DONE]" not in result.output

    flow_dirs = list((tmp_path / ".atelier" / "flows").iterdir())
    assert len(flow_dirs) == 1
    progress = json.loads((flow_dirs[0] / "progress.json").read_text())
    assert progress["run_path"] == str(project.resolve())
    logs = [json.loads(line) for line in (flow_dirs[0] / "logs.jsonl").read_text().splitlines()]
    assert logs[-1]["command"] == query
    assert logs[-1]["task"] == "chat"
    assert logs[-1]["tool"] == "harness:claude-code"
    assert "Blue it is." in logs[-1]["output"]


def test_ask_requires_a_path(tmp_path, monkeypatch) -> None:
    """The command refuses to start without an explicit target directory.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["ask", "hello"])
    assert result.exit_code == 2
    assert "--path" in unstyle(result.output)


def _wire_fake_agent(monkeypatch, turns: list[dict]) -> None:
    """Point the claude-code harness at the fake ACP agent with ``turns``.

    :param monkeypatch: pytest monkeypatch fixture.
    :param turns: list of turn dicts (``chunks``, ``stop``) the agent plays.
    """
    script = json.dumps({"turns": turns})
    monkeypatch.setenv(
        "ATELIER_CLAUDE_LAUNCH_CMD",
        json.dumps([sys.executable, str(FAKE_AGENT), "--script", script]),
    )


def test_ask_json_emits_ndjson_and_reads_stdin_replies(tmp_path, monkeypatch) -> None:
    """``--json`` round-trips an interactive session as parseable NDJSON.

    Agent chunks arrive as ``agent_message`` lines, each question as one
    ``agent_input_request`` line, and the run closes with a single
    ``flow_complete`` line. Stdin replies are consumed one per question.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    _wire_fake_agent(
        monkeypatch,
        [
            {"chunks": ["Which colour? "], "stop": "end_turn"},
            {"chunks": ["Blue it is. [ATELIER_DONE]"], "stop": "end_turn"},
        ],
    )

    result = CliRunner().invoke(
        app,
        ["ask", "pick a colour", "--path", str(project), "--json"],
        input="blue\n",
    )

    assert result.exit_code == 0, result.output

    # Every stdout line must parse as JSON with a ``type`` field.
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    assert all("type" in ev for ev in events)

    types = [ev["type"] for ev in events]
    assert "agent_message" in types
    assert "agent_input_request" in types
    assert types[-1] == "flow_complete"

    # The streamed prose is recoverable by concatenating agent_message text.
    agent_text = "".join(ev["text"] for ev in events if ev["type"] == "agent_message")
    assert "Which colour?" in agent_text
    assert "Blue it is." in agent_text
    # The done marker must never leak into the JSON stream.
    assert "[ATELIER_DONE]" not in agent_text

    # Exactly one input request, carrying a request_id and prompt.
    requests = [ev for ev in events if ev["type"] == "agent_input_request"]
    assert len(requests) == 1
    assert requests[0]["request_id"]
    assert requests[0]["prompt"]


def test_ask_json_reports_flow_failed_on_closed_stdin(tmp_path, monkeypatch) -> None:
    """A closed stdin at a prompt yields ``flow_failed``, not a hang.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    _wire_fake_agent(monkeypatch, [{"chunks": ["Which colour? "], "stop": "end_turn"}])

    # No input on stdin → EOF when the sink tries to read the reply.
    result = CliRunner().invoke(
        app,
        ["ask", "pick a colour", "--path", str(project), "--json"],
        input="",
    )

    assert result.exit_code == 1, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    assert events[-1]["type"] == "flow_failed"
    assert "unavailable" in events[-1]["error"].lower()


def test_ask_json_terminal_envelopes_carry_flow_id(tmp_path, monkeypatch) -> None:
    """``flow_complete`` carries the flow_id so a caller can log it.

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    _wire_fake_agent(
        monkeypatch,
        [{"chunks": ["Done. [ATELIER_DONE]"], "stop": "end_turn"}],
    )

    result = CliRunner().invoke(
        app,
        ["ask", "hello", "--path", str(project), "--json"],
        input="",
    )

    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    final = events[-1]
    assert final["type"] == "flow_complete"
    assert final["flow_id"]
    # flow_id is a real directory under .atelier/flows.
    assert (tmp_path / ".atelier" / "flows" / final["flow_id"]).is_dir()


def test_ask_default_output_is_unchanged_when_json_not_passed(tmp_path, monkeypatch) -> None:
    """Without ``--json`` the rich console view is used (no NDJSON on stdout).

    :param tmp_path: pytest temporary directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    project = tmp_path / "target-project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / ".atelier"))
    _wire_fake_agent(
        monkeypatch,
        [{"chunks": ["Done. [ATELIER_DONE]"], "stop": "end_turn"}],
    )

    result = CliRunner().invoke(
        app,
        ["ask", "hello", "--path", str(project)],
        input="",
    )

    assert result.exit_code == 0, result.output
    # Default mode does not emit JSON: stdout lines don't all parse as JSON.
    parsed_any = False
    for ln in result.output.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "flow_complete":
            parsed_any = True
    assert not parsed_any, "default mode leaked a flow_complete JSON envelope"


def test_stream_prompt_sink_strips_marker_split_across_chunks() -> None:
    """The done marker is stripped even when tokenized across chunks.

    :returns: None.
    """
    import asyncio
    import io

    from flow_atelier.services.executor.prompt_sink import StreamPromptSink

    out = io.StringIO()
    sink = StreamPromptSink(out=out, inp=io.StringIO())
    marker = "[ATELIER_DONE]"

    # Feed the marker split into arbitrary sub-token boundaries.
    chunks = ["7 is odd!\n\n[", "ATE", "LIER_", "DONE]", " and that's final"]
    for c in chunks:
        asyncio.run(sink.display(c))
    asyncio.run(sink.flush_steps())

    # Reassemble every emitted agent_message text in order.
    emitted = "".join(json.loads(ln)["text"] for ln in out.getvalue().splitlines() if ln.strip())
    assert marker not in emitted, f"marker leaked into stream: {emitted!r}"
    # No real content is dropped, only the marker itself.
    assert emitted == "7 is odd!\n\n and that's final"


def test_stream_prompt_sink_holds_partial_marker_then_flushes() -> None:
    """A chunk that only *starts* the marker is held, then flushed as text.

    :returns: None.
    """
    import asyncio
    import io

    from flow_atelier.services.executor.prompt_sink import StreamPromptSink

    out = io.StringIO()
    sink = StreamPromptSink(out=out, inp=io.StringIO())

    # "hello [ATELIER" ends mid-marker; nothing after should leak yet.
    asyncio.run(sink.display("hello [ATELIER"))
    partial = "".join(json.loads(ln)["text"] for ln in out.getvalue().splitlines() if ln.strip())
    assert "[ATELIER" not in partial  # held back, not emitted
    assert partial == "hello "

    # Completing the marker strips it; trailing real text is emitted.
    asyncio.run(sink.display("_DONE] done"))
    asyncio.run(sink.flush_steps())
    full = "".join(json.loads(ln)["text"] for ln in out.getvalue().splitlines() if ln.strip())
    assert "[ATELIER_DONE]" not in full
    assert full == "hello  done"
