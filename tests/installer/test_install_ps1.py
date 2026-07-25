"""Static regression guards for install.ps1.

These are text assertions, not execution: PowerShell is not available on the
Unix hosts this suite runs on, and the script's real path downloads a release
and edits the user's PATH. They are deliberately shallow — they prove only
that the two fixes on this branch have not been reverted, not that the script
works. Running install.ps1 end to end remains a Windows-CI gap.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INSTALL_PS1 = Path(__file__).resolve().parents[2] / "install.ps1"


@pytest.fixture(scope="module")
def script() -> str:
    """Return the installer source.

    :returns: install.ps1 contents.
    """
    return INSTALL_PS1.read_text(encoding="utf-8")


def test_null_user_path_is_guarded(script) -> None:
    """Verify a user with no user-level Path entry does not crash the script.

    ``GetEnvironmentVariable("Path", "User")`` returns ``$null`` for such a
    user, and ``$null.EndsWith(";")`` throws.

    :param script: install.ps1 contents.
    """
    assert 'GetEnvironmentVariable("Path", "User")' in script
    assert re.search(r'if \(-not \$CurrentPath\) \{ \$CurrentPath = "" \}', script), (
        "the $null guard before .EndsWith() is missing"
    )
    # The guard has to come before the first use.
    guard = script.index("if (-not $CurrentPath)")
    assert guard < script.index(".EndsWith("), "guard must precede .EndsWith()"


def test_conflicting_binary_warning_interpolates_the_property(script) -> None:
    """Verify the shadowing-binary warning prints the path, not the object.

    ``"  $found.Source"`` interpolates ``$found`` and then appends the literal
    text ``.Source``, so the warning named the wrong thing entirely. The
    subexpression form ``$($found.Source)`` is required.

    :param script: install.ps1 contents.
    """
    assert "$($found.Source)" in script
    # The buggy spelling ends the string straight after `.Source`; the fixed
    # one always has the closing paren of `$(...)` there instead.
    assert '$found.Source"' not in script, (
        "bare $found.Source inside a string interpolates the object, not the path"
    )
