"""`atelier add` command — install a conduit package from a repo or path."""
from __future__ import annotations

import typer
from rich.markup import escape

from flow_atelier.cli._shared import console
from flow_atelier.cli.main import app
from flow_atelier.core.atelier import Atelier
from flow_atelier.services.package import InstallReport, PackageError


def _print_report(report: InstallReport) -> None:
    """Render an install report in the spec's ``+``/``~`` format.

    :param report: the :class:`InstallReport` to render.
    """
    console.print(f"conduits → {escape(str(report.conduit_root))}")
    for name in report.conduits_installed:
        console.print(f"  [green]+[/green] {escape(name)}")
    for name in report.conduits_skipped:
        console.print(
            f"  [yellow]~[/yellow] {escape(name)}   (exists, skipped — use --force)"
        )
    roots = ", ".join(str(r) for r in report.skill_roots)
    console.print(f"skills → {escape(roots)}")
    for name in report.skills_installed:
        console.print(f"  [green]+[/green] {escape(name)}")
    for name in report.skills_skipped:
        console.print(
            f"  [yellow]~[/yellow] {escape(name)}   (exists, skipped — use --force)"
        )
    n_skipped = len(report.conduits_skipped) + len(report.skills_skipped)
    summary = (
        f"installed {len(report.conduits_installed)} conduits, "
        f"{len(report.skills_installed)} skills"
    )
    if n_skipped:
        summary += f" ({n_skipped} skipped)"
    console.print(f"[green]{summary}[/green]")
    if report.conduits_installed:
        console.print(
            f"[dim]run: atelier run {escape(report.conduits_installed[0])}[/dim]"
        )


@app.command("add", help="Install a conduit package from a git repo or local path.")
def add_cmd(
    source: str = typer.Argument(
        ..., help="git URL, owner/repo, or a local path."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing conduits/skills on collision."
    ),
    project: bool = typer.Option(
        False, "--project", help="Install conduits into the project store, not global."
    ),
    ref: str = typer.Option(
        None, "--ref", help="git branch/tag/commit to check out."
    ),
) -> None:
    """Fetch a package and install its conduits + skills.

    :param source: git URL, ``owner/repo`` shorthand, or a local path.
    :param force: overwrite colliding conduits/skills instead of skipping.
    :param project: install conduits into the project store rather than global.
    :param ref: optional git ref to check out.
    """
    try:
        report = Atelier().install_package(
            source, ref=ref, project=project, force=force
        )
    except PackageError as exc:
        console.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1)
    _print_report(report)
