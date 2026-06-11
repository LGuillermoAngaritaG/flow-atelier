"""Abstract HTTP server contract + DI helpers."""
from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from collections.abc import Iterable

from fastapi import FastAPI, HTTPException, Request

from flow_atelier.core.atelier import Atelier


class ApiServerBase(ABC):
    """Builds a FastAPI app bound to a single :class:`Atelier` instance."""

    @abstractmethod
    def create_app(
        self,
        atelier: Atelier,
        *,
        cors_origins: Iterable[str] | None = None,
        api_token: str | None = None,
    ) -> FastAPI:
        """Return a configured :class:`FastAPI` instance.

        :param atelier: facade to bind via dependency injection
        :param cors_origins: explicit CORS origins; ``None`` means
            localhost-only origins
        :param api_token: bearer token required on every request when set;
            ``None`` disables auth (local trust)
        """


def get_atelier(request: Request) -> Atelier:
    """FastAPI dependency: returns the :class:`Atelier` bound to the app.

    :param request: incoming FastAPI request whose app holds the facade
    """
    return request.app.state.atelier


def require_token(request: Request) -> None:
    """FastAPI dependency: enforce the bearer token when one is configured.

    :param request: incoming request whose app may hold ``state.api_token``
    :raises HTTPException: 401 when a token is set and the header is wrong
    """
    token = getattr(request.app.state, "api_token", None)
    if not token:
        return
    auth = request.headers.get("authorization", "")
    if not secrets.compare_digest(auth, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="invalid or missing API token")
