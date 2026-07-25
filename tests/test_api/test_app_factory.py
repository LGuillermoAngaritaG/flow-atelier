"""FastAPI app factory + DI tests."""
from __future__ import annotations

import httpx
import pytest

from flow_atelier.core.atelier import Atelier
from flow_atelier.services.api.app import FastApiServer


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    """Build an Atelier rooted at a temp directory.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.delenv("ATELIER_GLOBAL_ATELIER_DIR", raising=False)
    return Atelier(base_dir=tmp_path / ".atelier")


async def test_create_app_returns_fastapi_with_liveness(atelier):
    """Verify create_app returns a FastAPI instance that responds to requests.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        resp = await client.get("/flows")
    assert resp.status_code == 200


async def test_create_app_registers_cors(atelier):
    """Verify create_app registers CORS for an allowed origin.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier, cors_origins=["http://localhost:5173"])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        resp = await client.options(
            "/",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.headers.get("access-control-allow-origin") in (
        "http://localhost:5173",
        "*",
    )


async def test_create_app_default_cors_is_localhost_only(atelier):
    """Verify the default CORS policy allows localhost origins only —
    the API can run shell commands, so '*' would let any webpage drive it.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        ok = await client.options(
            "/",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert denied.headers.get("access-control-allow-origin") is None


async def test_forged_host_header_is_rejected(atelier):
    """Verify a foreign Host header is refused — this is the DNS-rebinding
    guard. CORS cannot catch it: a rebound hostname makes the attacker's page
    same-origin, so no Origin header is sent to reject. Without the Host pin,
    any site a user visits while `atelier serve` runs could POST /tasks/run.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        rebound = await client.get("/flows", headers={"host": "evil.example.com"})
        loopback = await client.get("/flows", headers={"host": "localhost:8000"})
    assert rebound.status_code == 400
    assert loopback.status_code == 200


async def test_allowed_hosts_override_is_honored(atelier):
    """Verify an explicit allowed_hosts list replaces the loopback default —
    `atelier serve --host <lan-ip>` has to keep reaching itself by that name.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier, allowed_hosts=["atelier.internal"])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        named = await client.get("/flows", headers={"host": "atelier.internal"})
        other = await client.get("/flows", headers={"host": "evil.example.com"})
    assert named.status_code == 200
    assert other.status_code == 400


async def test_ipv6_loopback_host_is_accepted(atelier):
    """Verify the bracketed IPv6 loopback Host reaches the API.

    A browser on ``http://[::1]:8000`` sends ``Host: [::1]:8000``. Starlette's
    TrustedHostMiddleware parses that as ``host.split(":")[0]`` -> ``[``, so
    the ``::1`` entry could never match and every request — including the
    WebSocket the UI needs — came back 400.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        bracketed = await client.get("/flows", headers={"host": "[::1]:8000"})
        bare = await client.get("/flows", headers={"host": "[::1]"})
        # An IPv6 literal that is not loopback is still refused.
        foreign = await client.get("/flows", headers={"host": "[2001:db8::1]:8000"})
    assert bracketed.status_code == 200
    assert bare.status_code == 200
    assert foreign.status_code == 400


async def test_host_check_is_case_insensitive(atelier):
    """Verify Host matching ignores case, as the header is case-insensitive.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        resp = await client.get("/flows", headers={"host": "LocalHost:8000"})
    assert resp.status_code == 200


async def test_forged_host_closes_the_websocket(atelier):
    """Verify a rejected WebSocket is closed, not handed an HTTP response.

    Sending `http.response.start` on a `websocket` scope is a protocol
    violation; the rebinding guard has to reach the WS route too, since
    that is the endpoint that actually runs conduits.

    :param atelier: atelier fixture.
    """
    from flow_atelier.services.api.app import HostHeaderMiddleware

    sent: list[dict] = []

    async def _app(scope, receive, send):
        """Downstream app that must never be reached.

        :param scope: ASGI scope.
        :param receive: ASGI receive channel.
        :param send: ASGI send channel.
        """
        raise AssertionError("forged host reached the WebSocket route")

    async def _send(message):
        """Capture what the middleware sent.

        :param message: ASGI message.
        """
        sent.append(message)

    mw = HostHeaderMiddleware(_app, ["localhost"])
    scope = {
        "type": "websocket",
        "headers": [(b"host", b"evil.example.com")],
    }
    await mw(scope, None, _send)
    assert sent == [{"type": "websocket.close", "code": 1008}]


def _client(app) -> httpx.AsyncClient:
    """Build an in-process httpx client for the given app.

    :param app: FastAPI instance under test.
    """
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


async def test_no_token_configured_allows_anonymous(atelier):
    """Without an api_token, requests need no Authorization header.

    :param atelier: atelier fixture.
    """
    app = FastApiServer().create_app(atelier)
    async with _client(app) as client:
        resp = await client.get("/flows")
    assert resp.status_code == 200


async def test_token_rejects_missing_or_wrong_bearer(atelier):
    """With an api_token set, missing or wrong bearers get 401.

    :param atelier: atelier fixture.
    """
    app = FastApiServer().create_app(atelier, api_token="s3cret")
    async with _client(app) as client:
        missing = await client.get("/flows")
        wrong = await client.get(
            "/flows", headers={"Authorization": "Bearer nope"}
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401


async def test_token_accepts_valid_bearer(atelier):
    """With an api_token set, the matching bearer is accepted.

    :param atelier: atelier fixture.
    """
    app = FastApiServer().create_app(atelier, api_token="s3cret")
    async with _client(app) as client:
        resp = await client.get(
            "/flows", headers={"Authorization": "Bearer s3cret"}
        )
    assert resp.status_code == 200
