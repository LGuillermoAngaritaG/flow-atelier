"""FastAPI app factory.

Builds a FastAPI instance bound to a single :class:`Atelier` facade.
Routes are mounted from :mod:`app.routes`. Business logic lives on the
facade; routes do at most: validate → call facade → serialize.
"""
from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.atelier import Atelier
from app.services.api.base import ApiServerBase


class FastApiServer(ApiServerBase):
    """Default :class:`ApiServerBase` implementation."""

    def create_app(
        self,
        atelier: Atelier,
        *,
        cors_origins: Iterable[str] | None = None,
    ) -> FastAPI:
        app = FastAPI(title="flow-atelier", version="0.1.0")
        app.state.atelier = atelier

        origins = list(cors_origins) if cors_origins else ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/")
        async def liveness() -> dict[str, str]:
            return {"status": "ok"}

        # Routes mount themselves below — imported here to avoid
        # circular imports between routes and the app factory.
        from app.routes import register_routes

        register_routes(app)
        return app
