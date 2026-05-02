"""Backwards-compat entry point for `atelier = app.main:app`."""
from app.cli import app

if __name__ == "__main__":
    app()
