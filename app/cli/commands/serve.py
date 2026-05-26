"""`atelier serve` command."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import typer

from app.cli._shared import console
from app.cli.main import app
from app.core.atelier import Atelier
from app.schemas.api import ScheduledJob
from app.schemas.log import TaskEvent
from app.services.api.app import FastApiServer
from app.services.api.scheduler_bus import SchedulerEventBus
from app.services.scheduler import SchedulerDaemon, default_local_zone


@app.command(
    "serve",
    help="Run the FastAPI HTTP + WebSocket server with the embedded scheduler.",
)
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(
        8000, "--port", help="Bind port (use 0 for an ephemeral port)."
    ),
    reload_interval: float = typer.Option(
        30.0, "--reload-interval",
        help="Seconds between schedule store rescans."
    ),
    cors_origin: list[str] = typer.Option(
        [], "--cors-origin",
        help="Allowed CORS origin (repeatable). Default = '*'."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level",
        help="Logging level for the server."
    ),
) -> None:
    """Run the FastAPI HTTP and WebSocket server with the embedded scheduler.

    :param host: bind host for the HTTP server.
    :param port: bind port (use 0 for an ephemeral port).
    :param reload_interval: seconds between schedule store rescans.
    :param cors_origin: allowed CORS origins (defaults to ``*`` when empty).
    :param log_level: logging level for uvicorn and the daemon.
    """
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )

    atelier = Atelier()
    bus = SchedulerEventBus()
    # The WS route subscribes new sockets to this bus so scheduled fires
    # (which don't originate from a connected socket) still reach UIs.
    atelier.scheduler_bus = bus  # type: ignore[attr-defined]

    async def _broadcasting_executor(job: ScheduledJob, working_dir: Path) -> None:
        """Run the conduit and fan lifecycle envelopes out to the bus."""
        base = {
            "schedule_id": job.id,
            "schedule_name": job.schedule.name,
            "conduit_name": job.conduit_name,
            "run_path": str(working_dir),
        }
        scheduled_atelier = Atelier(base_dir=working_dir / ".atelier")
        captured: dict[str, str | None] = {"flow_id": None}

        def _on_started(flow_id: str) -> None:
            captured["flow_id"] = flow_id
            asyncio.create_task(
                bus.broadcast(
                    {"type": "scheduled_run_started", "flow_id": flow_id, **base}
                )
            )

        def _on_task_event(event: TaskEvent) -> None:
            asyncio.create_task(
                bus.broadcast(
                    {
                        "type": "scheduled_task_event",
                        "flow_id": captured["flow_id"],
                        "event": event.model_dump(mode="json"),
                        **base,
                    }
                )
            )

        try:
            flow_id = await scheduled_atelier.run_conduit(
                job.conduit_name,
                dict(job.inputs),
                on_flow_started=_on_started,
                on_task_event=_on_task_event,
            )
        except Exception as e:  # noqa: BLE001
            await bus.broadcast(
                {
                    "type": "scheduled_run_failed",
                    "flow_id": captured["flow_id"],
                    "error": str(e),
                    **base,
                }
            )
            raise
        await bus.broadcast(
            {"type": "scheduled_run_complete", "flow_id": flow_id, **base}
        )

    daemon = SchedulerDaemon(
        atelier.schedule_store,
        executor=_broadcasting_executor,
        default_zone=default_local_zone(),
        default_working_dir=Path.cwd(),
        reload_interval_seconds=reload_interval,
    )
    # The schedules POST/DELETE handlers look here to opportunistically
    # re-sync the daemon when a schedule is created or removed.
    atelier.scheduler_daemon = daemon  # type: ignore[attr-defined]

    @asynccontextmanager
    async def _lifespan(app):
        """FastAPI lifespan context that starts and stops the scheduler daemon.

        :param app: the FastAPI application receiving the lifespan event.
        """
        await daemon.start()
        try:
            yield
        finally:
            await daemon.stop()

    cors = list(cors_origin) if cors_origin else None
    api_app = FastApiServer().create_app(atelier, cors_origins=cors)
    api_app.router.lifespan_context = _lifespan

    config = uvicorn.Config(
        api_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        lifespan="on",
    )
    server = uvicorn.Server(config)

    async def _run() -> None:
        """Start uvicorn and print the actual bind address once it is ready."""
        serve_task = asyncio.create_task(server.serve())
        # Wait for uvicorn to bind so we can print the actual port.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10.0
        while not server.started and loop.time() < deadline:
            await asyncio.sleep(0.05)
        actual = port
        try:
            if server.servers:
                actual = server.servers[0].sockets[0].getsockname()[1]
        except (AttributeError, IndexError, OSError):
            pass
        console.print(
            f"[green]atelier serve[/green] running at "
            f"[bold]http://{host}:{actual}[/bold]"
        )
        await serve_task

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
