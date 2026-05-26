"""/ws/run-conduit end-to-end tests."""
from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from app.core.atelier import Atelier
from app.services.api.app import FastApiServer

HELLO_YAML = """name: hello
description: Say hello
tasks:
  - greet:
      description: greet
      task: "echo hello-from-ws"
      tool: tool:bash
      depends_on: []
"""


HITL_YAML = """name: human
description: HITL
tasks:
  - ask:
      description: gate
      task: "Provide your answer"
      tool: tool:hitl
      depends_on: []
      inputs:
        choice: "Pick a value"
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Build an Atelier + FastAPI app pair with seeded conduits.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    global_dir = tmp_path / ".atelier-global"
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(global_dir))
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    for name, yaml_str in [("hello", HELLO_YAML), ("human", HITL_YAML)]:
        (atelier.store.global_dir / "conduits" / name).mkdir(
            parents=True, exist_ok=True
        )
        (
            atelier.store.global_dir / "conduits" / name / "conduit.yaml"
        ).write_text(yaml_str)
    app = FastApiServer().create_app(atelier)
    return atelier, app


def _drain_until(ws, predicate, *, max_messages: int = 50):
    """Read envelopes from a websocket until ``predicate`` matches.

    :param ws: websocket client.
    :param predicate: callable invoked per envelope; stop when it returns truthy.
    :param max_messages: cap on envelopes to read before raising.
    """
    collected: list[dict] = []
    for _ in range(max_messages):
        msg = ws.receive_text()
        envelope = json.loads(msg)
        collected.append(envelope)
        if predicate(envelope):
            return collected
    raise AssertionError(
        f"never received target envelope; got: {collected}"
    )


def test_ws_happy_path_emits_started_log_and_complete(env, tmp_path):
    """Verify the WS happy path emits started, log, and flow_complete envelopes.

    :param env: env fixture providing (atelier, app).
    :param tmp_path: pytest temp directory fixture.
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "run",
                        "flow_id": "T-1",
                        "conduit_name": "hello",
                        "inputs": {},
                        "run_path": str(tmp_path),
                    }
                )
            )
            envelopes = _drain_until(
                ws, lambda e: e["type"] == "flow_complete"
            )

    types = [e["type"] for e in envelopes]
    assert "started" in types
    assert "log" in types
    assert types[-1] == "flow_complete"
    log_envelopes = [e for e in envelopes if e["type"] == "log"]
    assert any(
        "hello-from-ws" in (entry["entry"].get("stdout") or "")
        for entry in log_envelopes
    )


def test_ws_hitl_round_trip_completes_after_answer(env, tmp_path):
    """Verify the WS hitl round-trip completes after an answer is sent.

    :param env: env fixture providing (atelier, app).
    :param tmp_path: pytest temp directory fixture.
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "run",
                        "flow_id": "T-2",
                        "conduit_name": "human",
                        "inputs": {},
                        "run_path": str(tmp_path),
                    }
                )
            )
            # Drain until we see the hitl_request.
            envelopes = _drain_until(
                ws, lambda e: e["type"] == "hitl_request"
            )
            assert envelopes[-1]["flow_id"] == "T-2"
            ws.send_text(
                json.dumps(
                    {
                        "type": "hitl_answer",
                        "flow_id": "T-2",
                        "answers": {"choice": "blue"},
                    }
                )
            )
            envelopes += _drain_until(
                ws, lambda e: e["type"] == "flow_complete"
            )

    assert envelopes[-1]["type"] == "flow_complete"


def test_ws_unknown_message_type_emits_error_envelope(env):
    """Verify an unknown WS message type emits an error envelope.

    :param env: env fixture providing (atelier, app).
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            ws.send_text(json.dumps({"type": "explode", "flow_id": "T-3"}))
            envelope = json.loads(ws.receive_text())
            assert envelope["type"] == "error"


def test_ws_run_unknown_conduit_emits_flow_failed(env, tmp_path):
    """Verify running an unknown conduit emits flow_failed or error.

    :param env: env fixture providing (atelier, app).
    :param tmp_path: pytest temp directory fixture.
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "run",
                        "flow_id": "T-4",
                        "conduit_name": "ghost",
                        "inputs": {},
                        "run_path": str(tmp_path),
                    }
                )
            )
            envelopes = _drain_until(
                ws, lambda e: e["type"] in ("flow_failed", "error")
            )
    assert envelopes[-1]["type"] in ("flow_failed", "error")
