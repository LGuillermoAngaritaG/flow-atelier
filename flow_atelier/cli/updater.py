"""Background auto-updater for frozen (PyInstaller) binaries.

Checks GitHub Releases for a newer version, downloads and verifies the
binary in a daemon thread, and swaps it in via an ``atexit`` handler —
so the update lands *after* the current command finishes and the process
exits (no ``.exe`` lock issues on Windows).

For ``pip``/``uv`` installs (``sys.frozen`` is falsy), prints an upgrade
hint to stderr instead.  Set ``ATELIER_NO_UPDATE_CHECK=1`` to disable
all update behaviour (useful in CI/tests).
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import sys
import threading
import urllib.request
from typing import Any

OWNER = "LGuillermoAngaritaG"
REPO = "flow-atelier"
RELEASES_API = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"

# Module-level state shared between the daemon thread and the atexit handler.
_pending_update: bytes | None = None
_pending_asset_name: str | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_frozen_binary() -> bool:
    """Return ``True`` when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _platform_asset_name() -> str:
    """Return the release asset name for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux" and machine == "x86_64":
        return "atelier-linux-x86_64"
    if system == "darwin":
        # GitHub macos-latest is arm64; Intel macs are rare now.
        if machine == "arm64":
            return "atelier-macos-arm64"
        return "atelier-macos-arm64"  # fall back to arm64 binary
    if system == "windows" and machine in ("amd64", "x86_64"):
        return "atelier-windows-x86_64.exe"

    raise RuntimeError(f"unsupported platform: {system}-{machine}")


def _fetch_json(url: str) -> Any:
    """Fetch *url* and return the parsed JSON response."""
    req = urllib.request.Request(url, headers={"User-Agent": "flow-atelier-updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def _fetch_bytes(url: str) -> bytes:
    """Fetch *url* and return the raw bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "flow-atelier-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def _download_and_verify(
    asset_url: str,
    asset_name: str,
    sums_url: str,
) -> bytes | None:
    """Download *asset_url*, verify its SHA-256 against *sums_url*, return bytes.

    Returns ``None`` on any failure (network error, hash mismatch, etc.).
    """
    try:
        binary = _fetch_bytes(asset_url)
        sums_text = _fetch_bytes(sums_url).decode("utf-8")
    except Exception:
        return None

    expected_hash: str | None = None
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == asset_name:
            expected_hash = parts[0]
            break

    if expected_hash is None:
        return None

    actual_hash = hashlib.sha256(binary).hexdigest()
    if actual_hash != expected_hash:
        return None

    return binary


# ---------------------------------------------------------------------------
# Daemon thread + atexit
# ---------------------------------------------------------------------------

def _background_check() -> None:
    """Run in a daemon thread: check for a newer version, download if found."""
    global _pending_update, _pending_asset_name  # noqa: PLW0603

    try:
        release = _fetch_json(RELEASES_API)
        remote_tag = release.get("tag_name", "")
        if not remote_tag:
            return

        remote_version = remote_tag.lstrip("v")

        from flow_atelier import __version__

        if remote_version <= __version__:
            return  # already up to date

        # Build asset download URLs from the release assets list.
        asset_name = _platform_asset_name()
        asset_url: str | None = None
        sums_url: str | None = None

        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name == asset_name:
                asset_url = asset.get("browser_download_url")
            elif name == "SHA256SUMS":
                sums_url = asset.get("browser_download_url")

        if not asset_url or not sums_url:
            return

        binary = _download_and_verify(asset_url, asset_name, sums_url)
        if binary is not None:
            with _lock:
                _pending_update = binary
                _pending_asset_name = asset_name
    except Exception:
        # Updater must never crash the CLI.
        pass


def _do_swap() -> None:
    """``atexit`` handler: replace the running binary with the downloaded one."""
    global _pending_update, _pending_asset_name  # noqa: PLW0603

    with _lock:
        binary = _pending_update
        asset_name = _pending_asset_name
        _pending_update = None
        _pending_asset_name = None

    if binary is None or asset_name is None:
        return

    try:
        current = os.path.realpath(sys.executable)
        backup = current + ".old"
        update_path = current  # replace in-place

        # Write the new binary to a temp location first.
        import tempfile

        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(current))
        try:
            os.write(fd, binary)
            os.close(fd)
            fd = -1

            # Rename old → .old (may fail on Windows if .old exists from a
            # previous update — that's fine, we just overwrite it).
            try:
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(current, backup)
            except OSError:
                # If we can't rename the old file, try direct replace.
                pass

            os.replace(tmp_path, update_path)
            tmp_path = None  # prevent cleanup in finally
        finally:
            if fd >= 0:
                os.close(fd)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception:
        # Swap failure must not crash on exit.
        pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_background_update_check() -> None:
    """Spawn the background update-check thread (or print a pip hint).

    Called from the CLI root callback.  No-op when
    ``ATELIER_NO_UPDATE_CHECK=1`` is set.
    """
    if os.environ.get("ATELIER_NO_UPDATE_CHECK") == "1":
        return

    if not is_frozen_binary():
        # pip / uv install — just hint the user.
        print(
            "Tip: run `uv tool upgrade flow-atelier` to check for updates.",
            file=sys.stderr,
        )
        return

    thread = threading.Thread(target=_background_check, daemon=True)
    thread.start()

    atexit.register(_do_swap)
