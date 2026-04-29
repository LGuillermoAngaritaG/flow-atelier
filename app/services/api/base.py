"""Abstract HTTP server contract + DI helper."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from fastapi import FastAPI, Request

from app.core.atelier import Atelier


class ApiServerBase(ABC):
    """Builds a FastAPI app bound to a single :class:`Atelier` instance."""

    @abstractmethod
    def create_app(
        self,
        atelier: Atelier,
        *,
        cors_origins: Iterable[str] | None = None,
    ) -> FastAPI:
        """Return a configured :class:`FastAPI` instance.

        :param atelier: facade to bind via dependency injection
        :param cors_origins: explicit CORS origins; ``None`` means ``["*"]``
        """


def get_atelier(request: Request) -> Atelier:
    """FastAPI dependency: returns the :class:`Atelier` bound to the app."""
    return request.app.state.atelier
