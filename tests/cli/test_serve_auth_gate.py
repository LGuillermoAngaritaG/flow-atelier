"""CLI test: `atelier serve` refuses an unauthenticated non-loopback bind.

The API can run shell commands, and `api_token` defaults to empty, so a bind
anything but loopback can reach is a remote code execution surface. A printed
warning scrolls past in the same second the port opens; this has to be a hard
stop.
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from flow_atelier.cli import app


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Isolated cwd and global dir so the command touches nothing real.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    :returns: the working directory path.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ATELIER_NO_UPDATE_CHECK", "1")
    monkeypatch.delenv("ATELIER_API_TOKEN", raising=False)
    return tmp_path


@pytest.fixture
def never_runs(monkeypatch):
    """Fail the test if uvicorn is ever actually started.

    :param monkeypatch: pytest monkeypatch fixture.
    """

    def _boom(*args, **kwargs):
        """Reject any attempt to bind a port.

        :param args: ignored.
        :param kwargs: ignored.
        """
        raise AssertionError("server started despite a missing token")

    monkeypatch.setattr("uvicorn.Server", _boom)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10"])
def test_non_loopback_bind_without_token_is_refused(
    workdir, never_runs, host
) -> None:
    """Verify a non-loopback bind with no token exits non-zero and explains.

    :param workdir: isolated working directory fixture.
    :param never_runs: guard asserting uvicorn never starts.
    :param host: bind address under test.
    """
    result = CliRunner().invoke(app, ["serve", "--host", host])
    assert result.exit_code == 1
    assert "ATELIER_API_TOKEN" in result.output


def test_non_loopback_bind_with_token_is_allowed(workdir, monkeypatch) -> None:
    """Verify a token unblocks the bind — the gate is auth, not the address.

    :param workdir: isolated working directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setenv("ATELIER_API_TOKEN", "s3cret")
    started: list[str] = []

    class _Server:
        """Stand-in that records the bind instead of opening a socket."""

        def __init__(self, config):
            """Record the configured host.

            :param config: uvicorn config built by the command.
            """
            started.append(config.host)
            self.started = True
            self.servers = []

        async def serve(self):
            """Pretend to serve, then return immediately."""
            return None

    monkeypatch.setattr("uvicorn.Server", _Server)
    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 0, result.output
    assert started == ["0.0.0.0"]


def test_loopback_bind_needs_no_token(workdir, monkeypatch) -> None:
    """Verify the default local workflow is untouched by the gate.

    :param workdir: isolated working directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    started: list[str] = []

    class _Server:
        """Stand-in that records the bind instead of opening a socket."""

        def __init__(self, config):
            """Record the configured host.

            :param config: uvicorn config built by the command.
            """
            started.append(config.host)
            self.started = True
            self.servers = []

        async def serve(self):
            """Pretend to serve, then return immediately."""
            return None

    monkeypatch.setattr("uvicorn.Server", _Server)
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0, result.output
    assert started == ["127.0.0.1"]
