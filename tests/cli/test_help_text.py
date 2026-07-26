"""Tests for AtelierTyper deriving --help text from command docstrings."""
from __future__ import annotations

from flow_atelier.cli.main import AtelierTyper, _help_from_doc


def test_sphinx_field_list_is_stripped() -> None:
    """Verify `:param:` blocks never reach a user reading --help."""
    doc = "Halt a running flow.\n\n:param flow_id: id to halt.\n:returns: nothing.\n"
    assert _help_from_doc(doc) == "Halt a running flow."


def test_double_backticks_downgraded() -> None:
    """Verify rst literals render as single backticks in a terminal."""
    assert _help_from_doc("Use ``--force`` to skip.") == "Use `--force` to skip."


def test_help_is_not_leaked_between_commands() -> None:
    """Verify a reused decorator does not carry the first command's help.

    `command()` closes over its `kwargs`; writing the derived help into that
    dict rather than a copy pinned the first function's docstring onto every
    later one registered through the same decorator object.
    """
    app = AtelierTyper()
    decorator = app.command()

    @decorator
    def first() -> None:
        """First command prose."""

    @decorator
    def second() -> None:
        """Second command prose."""

    helps = {c.callback.__name__: c.help for c in app.registered_commands}
    assert helps["first"] == "First command prose."
    assert helps["second"] == "Second command prose."


def test_explicit_help_still_wins() -> None:
    """Verify an explicit `help=` on the decorator overrides the docstring."""
    app = AtelierTyper()

    @app.command(help="explicit")
    def cmd() -> None:
        """Docstring prose that must not be used."""

    assert app.registered_commands[0].help == "explicit"
