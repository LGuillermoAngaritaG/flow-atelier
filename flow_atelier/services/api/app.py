"""FastAPI app factory.

Builds a FastAPI instance bound to a single :class:`Atelier` facade.
Routes are mounted from :mod:`flow_atelier.routes`. Business logic lives on the
facade; routes do at most: validate → call facade → serialize.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from flow_atelier import __version__
from flow_atelier.core.atelier import Atelier
from flow_atelier.services.api.base import ApiServerBase

_STATIC_DIR = Path(__file__).resolve().parents[3] / "dist"


class FastApiServer(ApiServerBase):
    """Default :class:`ApiServerBase` implementation."""

    def create_app(
        self,
        atelier: Atelier,
        *,
        cors_origins: Iterable[str] | None = None,
        api_token: str | None = None,
    ) -> FastAPI:
        """Build the FastAPI app, attach CORS, and register all routes.

        :param atelier: facade exposed via ``app.state.atelier``
        :param cors_origins: explicit CORS origins; ``None`` means
            localhost-only origins (the API can run shell commands, so a
            wildcard would let any webpage drive it cross-origin)
        :param api_token: bearer token required on every request when set;
            ``None`` disables auth (local trust)
        """
        app = FastAPI(title="flow-atelier", version=__version__)
        app.state.atelier = atelier
        app.state.api_token = api_token or ""

        if cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=list(cors_origins),
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        else:
            app.add_middleware(
                CORSMiddleware,
                allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Routes mount themselves below — imported here to avoid
        # circular imports between routes and the app factory.
        from flow_atelier.routes import register_routes

        register_routes(app)

        # SPA static files — registered last so API/WS routes take priority.
        if _STATIC_DIR.is_dir():

            app.mount(
                "/assets",
                StaticFiles(directory=_STATIC_DIR / "assets"),
                name="spa-assets",
            )

            @app.get("/favicon.svg")
            async def _favicon():
                return FileResponse(_STATIC_DIR / "favicon.svg")

            @app.get("/{full_path:path}")
            async def _spa_fallback(full_path: str):
                return FileResponse(_STATIC_DIR / "index.html")

        return app
