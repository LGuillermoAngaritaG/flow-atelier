"""Shared CLI helpers — package-internal.

Nothing outside ``app.cli`` should import from this module.
"""
from __future__ import annotations

from datetime import datetime

import typer
from rich.console import Console

from app.core.atelier import Atelier
from app.core.settings import AtelierSettings
from app.schemas.progress import Progress
from app.services.scheduler import ScheduleStore

console = Console()


def _parse_inputs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            raise typer.BadParameter(f"--input expects key=value, got {p!r}")
        key, value = p.split("=", 1)
        out[key] = value
    return out


def _resolve_flow_id(atelier: Atelier, candidate: str) -> str:
    """Resolve ``candidate`` to a full flow id, supporting git-style prefixes.

    - Exact id present on disk → returned as-is.
    - Otherwise scans all known flows. Exactly one prefix match → that id.
    - Zero matches → exits with ``unknown flow`` (code 1).
    - More than one → exits with ``ambiguous flow id`` and lists candidates.
    """
    all_flows = atelier.list_flows()
    if candidate in all_flows:
        return candidate
    matches = [fid for fid in all_flows if fid.startswith(candidate)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        console.print(f"[red]unknown flow:[/red] {candidate}")
        raise typer.Exit(code=1)
    console.print(f"[red]ambiguous flow id:[/red] {candidate} matches:")
    for m in matches[:10]:
        console.print(f"  - {m}")
    if len(matches) > 10:
        console.print(f"  … and {len(matches) - 10} more")
    raise typer.Exit(code=1)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Engine emits Z-suffixed ISO; fromisoformat handles +00:00 form.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_duration_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds:.2f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _flow_duration_seconds(progress: Progress) -> float | None:
    start = _parse_iso(progress.started_at)
    end = _parse_iso(progress.finished_at) if progress.finished_at else None
    if start is None:
        return None
    if end is None:
        # In-flight: don't try to compute against wall-clock here — just omit.
        return None
    return (end - start).total_seconds()


def _format_clock(ts: str | None) -> str:
    dt = _parse_iso(ts)
    if dt is None:
        return "—"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _format_next_fire(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z").strip()


def _schedule_store() -> ScheduleStore:
    settings = AtelierSettings()
    return ScheduleStore(settings.atelier_dir)
