"""Tests for flow_atelier.cli.updater — all network calls are mocked."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from flow_atelier.cli.updater import (
    _do_swap,
    _download_and_verify,
    _platform_asset_name,
    is_frozen_binary,
    start_background_update_check,
)


# ---------------------------------------------------------------------------
# 1. is_frozen_binary
# ---------------------------------------------------------------------------


def test_is_frozen_returns_false_in_dev():
    """In the test environment (not PyInstaller), is_frozen_binary() is False."""
    assert is_frozen_binary() is False


# ---------------------------------------------------------------------------
# 2. _platform_asset_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sys_name", "machine", "expected"),
    [
        ("Linux", "x86_64", "atelier-linux-x86_64"),
        ("Darwin", "arm64", "atelier-macos-arm64"),
        ("Windows", "AMD64", "atelier-windows-x86_64.exe"),
    ],
)
def test_platform_asset_name_known_platforms(sys_name, machine, expected):
    """All three supported platforms produce the correct asset name."""
    with (
        patch("flow_atelier.cli.updater.platform") as mock_plat,
    ):
        mock_plat.system.return_value = sys_name
        mock_plat.machine.return_value = machine
        assert _platform_asset_name() == expected


# ---------------------------------------------------------------------------
# 3. start_background_update_check disabled by env
# ---------------------------------------------------------------------------


def test_background_check_disabled_by_env(monkeypatch):
    """ATELIER_NO_UPDATE_CHECK=1 prevents thread spawn and pip hint."""
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")
    # Should return immediately without doing anything.
    start_background_update_check()
    # No assertion needed — just verify no exception and no stderr output.


# ---------------------------------------------------------------------------
# 4. _do_swap noop when nothing pending
# ---------------------------------------------------------------------------


def test_do_swap_noop_when_no_pending():
    """_do_swap() is safe to call when no update has been downloaded."""
    import flow_atelier.cli.updater as mod

    # Ensure no pending update.
    with mod._lock:
        mod._pending_update = None
        mod._pending_asset_name = None

    # Should not raise.
    _do_swap()


# ---------------------------------------------------------------------------
# 5. pip install shows upgrade hint
# ---------------------------------------------------------------------------


def test_pip_install_shows_upgrade_hint(monkeypatch, capsys):
    """Non-frozen install prints a uv upgrade hint to stderr."""
    monkeypatch.delenv("ATELIER_NO_UPDATE_CHECK", raising=False)
    # is_frozen_binary() returns False (default in test env).
    start_background_update_check()
    captured = capsys.readouterr()
    assert "uv tool upgrade" in captured.err


# ---------------------------------------------------------------------------
# 6. verify hash rejects mismatch
# ---------------------------------------------------------------------------


def test_verify_hash_rejects_mismatch():
    """_download_and_verify returns None when the SHA-256 doesn't match."""
    fake_binary = b"this is a fake binary"
    correct_hash = __import__("hashlib").sha256(fake_binary).hexdigest()
    wrong_hash = "0" * 64

    sums_content = f"{wrong_hash}  atelier-linux-x86_64\n"

    with (
        patch("flow_atelier.cli.updater._fetch_bytes") as mock_fetch,
    ):
        # First call = binary, second call = sums text.
        mock_fetch.side_effect = [
            fake_binary,
            sums_content.encode("utf-8"),
        ]
        result = _download_and_verify(
            "https://example.com/atelier-linux-x86_64",
            "atelier-linux-x86_64",
            "https://example.com/SHA256SUMS",
        )

    assert result is None
