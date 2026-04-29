"""FastAPI routers.

Each module mounts a single router for one resource. The
:func:`register_routes` helper attaches each router to the app, kept in
this module so the app factory and ``atelier serve`` command share one
mount point.
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Register every resource router on the given FastAPI app."""
    # Local imports keep optional deps (websockets, etc.) lazy.
    return None
