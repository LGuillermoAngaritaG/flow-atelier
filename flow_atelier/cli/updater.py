"""Background auto-updater for frozen (PyInstaller) binaries.

Checks GitHub Releases for a newer version, downloads and verifies the
binary in a daemon thread, and swaps it in via an ``atexit`` handler —
so the update lands *after* the current command finishes and the process
exits (no ``.exe`` lock issues on Windows).

For ``pip``/``uv`` installs (``sys.frozen`` is falsy), prints an upgrade
hint to stderr instead.  Set ``ATELIER_NO_UPDATE_CHECK=1`` to disable
all update behaviour (useful in CI/tests).

Trust model: the downloaded binary is verified only against a
``SHA256SUMS`` file fetched from the same GitHub release over HTTPS.
That detects transport corruption but not a tampered release — there is
no client-verifiable signature, so the integrity of an update rests
entirely on GitHub release integrity plus TLS, not on a key the client
holds. This is an accepted limitation for this project.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import sys
import threading
import time
import urllib.request
from pathlib import Path
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


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple of ints.

    Strips a leading ``v``. Non-numeric/garbage parts make the whole
    version sort as ``(-1,)`` so the caller fails closed (treats it as
    "not newer") instead of crashing on an unparseable release tag.
    """
    v = v.strip().lstrip("v")
    try:
        return tuple(int(part) for part in v.split("."))
    except ValueError:
        return (-1,)


def _platform_asset_name() -> str:
    """Return the release asset name for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux" and machine == "x86_64":
        return "atelier-linux-x86_64"
    if system == "darwin":
        # Only an arm64 build is published; Intel macs cannot run it and
        # there is no Rosetta fallback (consistent with install.sh).
        if machine == "arm64":
            return "atelier-macos-arm64"
        raise RuntimeError(f"unsupported platform: {system}-{machine}")
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

        from flow_atelier import __version__

        if _parse_version(remote_tag) <= _parse_version(__version__):
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

            # mkstemp creates the temp file 0600 (not executable); os.replace
            # would carry that mode onto the live binary and brick the next
            # run. Match the currently-running binary's mode (fall back to
            # 0755) so the swapped-in file stays executable.
            try:
                os.chmod(tmp_path, os.stat(current).st_mode)
            except OSError:
                os.chmod(tmp_path, 0o755)

            # Rename old → .old (may fail on Windows if .old exists from a
            # previous update — that's fine, we just overwrite it).
            renamed_backup = False
            try:
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(current, backup)
                renamed_backup = True
            except OSError:
                # If we can't rename the old file, try direct replace.
                pass

            try:
                os.replace(tmp_path, update_path)
            except Exception:
                # The live path may now be empty (we already moved the
                # original to .old). Roll the backup back into place so a
                # botched swap leaves a runnable binary instead of a hole.
                if renamed_backup:
                    try:
                        os.replace(backup, current)
                    except Exception:
                        pass
                raise
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

CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_STAMP_PATH = Path.home() / ".atelier" / ".last-update-check"


def _due_for_check(now: float) -> bool:
    """Return True at most once per :data:`CHECK_INTERVAL_SECONDS`, and stamp it.

    Without this the hint prints on *every* command (noise in scripts and
    pipes) and the frozen binary calls the GitHub API on every invocation,
    which burns the 60/hour unauthenticated rate limit. A stamp that can't be
    read or written fails open: the check runs, it just isn't throttled.

    :param now: current wall-clock time, seconds since the epoch.
    :returns: True when a check should run now.
    """
    try:
        if now - _STAMP_PATH.stat().st_mtime < CHECK_INTERVAL_SECONDS:
            return False
    except OSError:
        pass  # missing or unreadable stamp — treat as due
    try:
        _STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STAMP_PATH.touch()
    except OSError:
        pass  # read-only HOME: check every time rather than never
    return True


def start_background_update_check() -> None:
    """Spawn the background update-check thread (or print a pip hint).

    Called from the CLI root callback.  No-op when
    ``ATELIER_NO_UPDATE_CHECK=1`` is set, and throttled to once a day.
    """
    if os.environ.get("ATELIER_NO_UPDATE_CHECK") == "1":
        return

    if not _due_for_check(time.time()):
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
