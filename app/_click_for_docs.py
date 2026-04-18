"""Expose the Typer CLI as a plain Click command so ``mkdocs-click`` can
introspect it for the auto-generated CLI reference page.

Kept deliberately tiny: it imports the Typer ``app`` object from
``app.main`` and re-exports the Click equivalent. No runtime logic should
live here — if the docs plugin ever breaks, this module should remain a
one-liner translation.
"""
from __future__ import annotations

import typer

from app.main import app

cli = typer.main.get_command(app)
