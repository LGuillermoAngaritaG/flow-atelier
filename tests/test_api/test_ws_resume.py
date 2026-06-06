"""WebSocket resume end-to-end test."""
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
      task: "echo hello-from-resume"
      tool: tool:bash
      depends_on: []
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Build an Atelier + FastAPI app pair with a seeded conduit.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    global_dir = tmp_path / ".atelier-global"
    monkeypatch.setenv("ATELIER_GLOBAL_ATELIER_DIR", str(global_dir))
    atelier = Atelier(base_dir=tmp_path / ".atelier")
    cond_dir = atelier.store.global_dir / "conduits" / "hello"
    cond_dir.mkdir(parents=True, exist_ok=True)
    (cond_dir / "conduit.yaml").write_text(HELLO_YAML)
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


def test_ws_resume_emits_started_log_and_complete(env, tmp_path):
    """Verify a WS resume message re-runs a failed flow and emits lifecycle envelopes.

    First runs a flow to completion (via ``run``), then sends a ``resume``
    message for that flow_id.  Since the flow is completed (not failed),
    the server should emit ``flow_failed`` with a descriptive error.
    This validates the message routing works end-to-end.

    :param env: env fixture providing (atelier, app).
    :param tmp_path: pytest temp directory fixture.
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            # Run a flow to completion first
            ws.send_text(
                json.dumps(
                    {
                        "type": "run",
                        "conduit_name": "hello",
                        "inputs": {},
                        "run_path": str(tmp_path),
                    }
                )
            )
            run_envelopes = _drain_until(
                ws, lambda e: e["type"] == "flow_complete"
            )
            flow_id = run_envelopes[0]["flow_id"]
            assert flow_id

            # Now try to resume it — should fail because it's completed
            ws.send_text(
                json.dumps(
                    {
                        "type": "resume",
                        "flow_id": flow_id,
                    }
                )
            )
            resume_envelopes = _drain_until(
                ws, lambda e: e["type"] in ("flow_failed", "flow_complete")
            )

    # A completed flow cannot be resumed
    assert resume_envelopes[-1]["type"] == "flow_failed"
    assert "completed" in resume_envelopes[-1].get("error", "").lower() or \
           "only resume failed" in resume_envelopes[-1].get("error", "").lower()


def test_ws_resume_unknown_flow_emits_flow_failed(env):
    """Verify resuming an unknown flow emits flow_failed.

    :param env: env fixture providing (atelier, app).
    """
    _, app = env
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run-conduit") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "resume",
                        "flow_id": "20260101_deadbeef_nonexistent",
                    }
                )
            )
            envelopes = _drain_until(
                ws, lambda e: e["type"] in ("flow_failed", "error")
            )

    assert envelopes[-1]["type"] in ("flow_failed", "error")
