"""`atelier channels` sub-app — list, sessions, reset."""
from __future__ import annotations

import time
from pathlib import Path

import typer
import yaml

from app.cli._shared import console
from app.cli.main import channels_app
from app.core.settings import AtelierSettings
from app.schemas.channels_file import ChannelsFile
from app.services.channels.sessions import (
    DEFAULT_TTL_SECONDS,
    ChannelSessionStore,
)


def _atelier_dir() -> Path:
    return AtelierSettings().atelier_dir


def _channels_path() -> Path:
    settings = AtelierSettings()
    if settings.channels_config_path is not None:
        return Path(settings.channels_config_path)
    return settings.atelier_dir / "channels.yaml"


@channels_app.command("list", help="Show configured channels and bindings.")
def channels_list_cmd() -> None:
    path = _channels_path()
    if not path.exists():
        console.print(
            "[yellow]no channels.yaml found[/yellow] — channel adapters disabled."
        )
        return
    cfg = ChannelsFile.model_validate(yaml.safe_load(path.read_text()) or {})
    if not cfg.channels:
        console.print("[yellow]channels.yaml has no channels declared[/yellow]")
        return
    for ch in cfg.channels:
        console.print(
            f"[bold]{ch.name}[/bold] ({ch.kind.value}) "
            f"token_env=[cyan]{ch.token_env}[/cyan]"
        )
    if cfg.bindings:
        console.print("\n[bold]bindings:[/bold]")
        for b in cfg.bindings:
            console.print(f"  {b.channel} → {b.conduit}")


@channels_app.command(
    "sessions", help="List persisted channel session ids and their TTL."
)
def channels_sessions_cmd() -> None:
    store = ChannelSessionStore(atelier_dir=_atelier_dir())
    entries = store._read_all()
    if not entries:
        console.print("[dim]no sessions persisted[/dim]")
        return
    now = time.time()
    for key in sorted(entries):
        entry = entries[key]
        last = float(entry.get("last_active_at", 0))
        age_seconds = max(0, int(now - last))
        ttl_seconds = max(0, DEFAULT_TTL_SECONDS - age_seconds)
        sid = entry.get("session_id", "?")
        console.print(
            f"{key}  session_id=[cyan]{sid}[/cyan]  "
            f"ttl={ttl_seconds // 3600}h{(ttl_seconds % 3600) // 60}m"
        )


@channels_app.command(
    "reset", help="Clear stored sessions for a session_key (forces /new)."
)
def channels_reset_cmd(
    session_key: str = typer.Argument(
        ..., help="The session_key to clear (e.g. chat_id for Telegram)."
    ),
) -> None:
    store = ChannelSessionStore(atelier_dir=_atelier_dir())
    # Match any channel — clear "<channel>:<session_key>:" prefixes by
    # walking entries.
    entries = store._read_all()
    to_clear_prefixes: set[str] = set()
    for key in entries:
        parts = key.split(":")
        if len(parts) >= 3 and parts[1] == session_key:
            to_clear_prefixes.add(f"{parts[0]}:{session_key}:")
    total = 0
    for prefix in to_clear_prefixes:
        total += store.clear_prefix(prefix)
    console.print(f"cleared {total} session entr{'y' if total == 1 else 'ies'}")
