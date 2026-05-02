"""Typer CLI entrypoint for flow-atelier."""
from __future__ import annotations

from app.cli import app
from app.cli.render import _render_task_event, _truncate_tail  # noqa: F401


if __name__ == "__main__":
    app()
