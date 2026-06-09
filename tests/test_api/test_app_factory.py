"""FastAPI app factory + DI tests."""
from __future__ import annotations

import httpx
import pytest

from app.core.atelier import Atelier
from app.services.api.app import FastApiServer


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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/flows")
    assert resp.status_code == 200


async def test_create_app_registers_cors(atelier):
    """Verify create_app registers CORS for an allowed origin.

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier, cors_origins=["http://localhost:5173"])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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


async def test_create_app_default_cors_is_wildcard(atelier):
    """Verify the default CORS policy is wildcard (or echoed origin).

    :param atelier: atelier fixture.
    """
    server = FastApiServer()
    app = server.create_app(atelier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    # Either wildcard or echoed origin is acceptable.
    allow = resp.headers.get("access-control-allow-origin")
    assert allow in ("*", "http://example.com")
