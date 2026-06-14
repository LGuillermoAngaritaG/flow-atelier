"""`atelier run` command."""
from __future__ import annotations

import asyncio
import sys

import typer
import yaml
from pydantic import ValidationError
from rich.markup import escape

from flow_atelier.cli._shared import _parse_inputs, _resolve_flow_id, console
from flow_atelier.cli.main import app
from flow_atelier.cli.rendering.render import (
    _render_orchestration_msg,
    _render_run_footer,
    _render_task_event,
    format_conduit_error,
)
from flow_atelier.core.atelier import Atelier
from flow_atelier.schemas.flow import parse_flow_id
from flow_atelier.schemas.log import TaskEvent


@app.command(
    "run",
    help=(
        "Start a new flow for the named conduit. "
        "Use --input key=value to pass inputs. "
        "Use --resume <flow_id> to pick up a failed or crashed run."
    ),
)
def run_cmd(
    conduit_name: str = typer.Argument(
        None, help="Name of the conduit to run (not needed with --resume)."
    ),
    inputs_raw: list[str] = typer.Option(
        [],
        "--input",
        "-i",
        help="key=value input (repeatable).",
    ),
    show_steps: bool = typer.Option(
        True,
        "--show-steps/--hide-steps",
        help="Stream intermediate thinking and tool activity live (default: on).",
    ),
    resume_from: str | None = typer.Option(
        None,
        "--resume",
        help="Resume a failed or crashed flow by its id (supports prefix matching).",
    ),
) -> None:
    """Start a new flow or resume a failed one.

    :param conduit_name: name of the conduit to execute.
    :param inputs_raw: list of ``key=value`` input strings collected from ``--input``.
    :param show_steps: when true, stream intermediate thinking and tool activity live.
    :param resume_from: flow id (or unique prefix) of a failed run to resume.
    """
    atelier = Atelier()

    # --resume path: resolve the old flow, skip input prompts
    if resume_from is not None:
        flow_id = _resolve_flow_id(atelier, resume_from)
        # Surface a malformed conduit with a readable message before resuming,
        # so a YAML/schema/name error doesn't reach the generic `flow failed:`
        # handler as a raw exception. read_conduit is the only conduit-load
        # surface; resume_flow's own ValueError (e.g. "can only resume failed
        # or crashed flows") is unrelated and must keep its generic handling.
        resume_conduit = parse_flow_id(flow_id)[0]
        try:
            atelier.store.read_conduit(resume_conduit)
        except FileNotFoundError:
            pass
        except (yaml.YAMLError, ValidationError, ValueError) as exc:
            console.print(
                f"[red]invalid conduit:[/red] {escape(format_conduit_error(exc))}"
            )
            console.print(f"[dim]→ fix conduits/{resume_conduit}/conduit.yaml[/dim]")
            raise typer.Exit(code=1)
        collected_events: list[TaskEvent] = []
        captured_flow_id: dict[str, str | None] = {"id": flow_id}

        def _on_event(event: TaskEvent) -> None:
            collected_events.append(event)
            _render_task_event(event, console)

        def _on_started(fid: str) -> None:
            captured_flow_id["id"] = fid

        def _on_task_starting(task_name: str, tool: str) -> None:
            console.print(_render_orchestration_msg(f'resuming task "{task_name}" [{tool}]'))

        console.print(_render_orchestration_msg(f'resuming flow {flow_id}'))
        try:
            result_id = asyncio.run(
                atelier.resume_flow(
                    flow_id,
                    on_task_event=_on_event,
                    on_flow_started=_on_started,
                    on_task_starting=_on_task_starting,
                    show_steps=show_steps,
                    stoppable=True,
                )
            )
        except asyncio.CancelledError:
            # SIGTERM via `atelier stop`: engine has marked the flow stopped.
            _render_run_footer(collected_events, console)
            console.print("[yellow]flow stopped[/yellow]")
            stopped_id = captured_flow_id["id"]
            if stopped_id:
                console.print(f"[yellow]flow_id:[/yellow] {stopped_id}")
            raise typer.Exit(code=0)
        except Exception as e:  # noqa: BLE001
            _render_run_footer(collected_events, console)
            console.print(f"[red]flow failed:[/red] {e}")
            raise typer.Exit(code=1)
        _render_run_footer(collected_events, console)
        console.print(f"[green]flow_id:[/green] {result_id}")
        return

    # --- normal run path (no --resume) ---

    if conduit_name is None:
        console.print("[red]error:[/red] conduit name is required (unless using --resume)")
        raise typer.Exit(code=1)

    inputs = _parse_inputs(inputs_raw)

    try:
        conduit = atelier.store.read_conduit(conduit_name)
    except FileNotFoundError:
        console.print(
            f"[red]unknown conduit:[/red] {conduit_name} "
            f"— try 'atelier list conduits'"
        )
        raise typer.Exit(code=1)
    except (yaml.YAMLError, ValidationError, ValueError) as exc:
        console.print(
            f"[red]invalid conduit:[/red] {escape(format_conduit_error(exc))}"
        )
        console.print(f"[dim]→ fix conduits/{conduit_name}/conduit.yaml[/dim]")
        raise typer.Exit(code=1)

    # Readiness gate: refuse to start an unrunnable conduit (unregistered tool
    # or a harness CLI missing from PATH) before prompting for inputs or
    # spending any wall-clock/tokens.
    problems = atelier.tool_readiness(conduit)
    if problems:
        for problem in problems:
            console.print(f"[red]cannot run:[/red] {escape(problem)}")
        raise typer.Exit(code=1)

    # Prompt for missing inputs when running interactively.
    missing = [
        k
        for k, spec in conduit.inputs.items()
        if k not in inputs and spec.default is None
    ]
    if missing and sys.stdin.isatty():
        from flow_atelier.cli.rendering.multiline_input import multiline_input_sync

        try:
            for key in missing:
                value = multiline_input_sync(
                    f"  {key} ({conduit.inputs[key].description}): ",
                    hint="Alt+Enter to submit",
                )
                inputs[key] = value
        except KeyboardInterrupt:
            print()
            raise typer.Exit(code=130)

    collected_events = []
    captured_flow_id = {"id": None}

    def _on_event(event: TaskEvent) -> None:
        """Collect the task event and render it to the console.

        :param event: the emitted task event to record and display.
        """
        collected_events.append(event)
        _render_task_event(event, console)

    def _on_started(fid: str) -> None:
        """Capture the flow id and print a start banner.

        :param fid: the flow id assigned when the run begins.
        """
        captured_flow_id["id"] = fid
        console.print(_render_orchestration_msg(f'starting flow {fid}'))

    def _on_task_starting(task_name: str, tool: str) -> None:
        """Announce that a task is about to run.

        :param task_name: name of the task starting.
        :param tool: tool identifier used to execute the task.
        """
        console.print(_render_orchestration_msg(f'running task "{task_name}" [{tool}]'))

    console.print(_render_orchestration_msg(f'loading conduit "{conduit_name}"'))

    try:
        flow_id = asyncio.run(
            atelier.run_conduit(
                conduit_name,
                inputs,
                on_task_event=_on_event,
                on_flow_started=_on_started,
                on_task_starting=_on_task_starting,
                show_steps=show_steps,
                stoppable=True,
            )
        )
    except asyncio.CancelledError:
        # SIGTERM via `atelier stop`: engine has marked the flow stopped.
        _render_run_footer(collected_events, console)
        console.print("[yellow]flow stopped[/yellow]")
        stopped_id = captured_flow_id["id"]
        if stopped_id:
            console.print(f"[yellow]flow_id:[/yellow] {stopped_id}")
        raise typer.Exit(code=0)
    except Exception as e:  # noqa: BLE001
        _render_run_footer(collected_events, console)
        console.print(f"[red]flow failed:[/red] {e}")
        fid = captured_flow_id["id"]
        if fid:
            console.print(f"[red]flow_id:[/red] {fid}")
            console.print(f"[dim]→ atelier run --resume {fid}[/dim]")
        raise typer.Exit(code=1)
    _render_run_footer(collected_events, console)
    console.print(f"[green]flow_id:[/green] {flow_id}")
