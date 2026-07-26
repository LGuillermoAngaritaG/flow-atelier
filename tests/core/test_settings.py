"""Settings unit tests."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from flow_atelier.core.settings import AtelierSettings


def test_defaults(tmp_path, monkeypatch):
    """Verify AtelierSettings exposes the expected defaults with no env overrides.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
    # Clear any ATELIER_* env vars that may leak in
    for k in list(__import__("os").environ):
        if k.startswith("ATELIER_"):
            monkeypatch.delenv(k, raising=False)
    s = AtelierSettings(_env_file=None)
    assert s.default_timeout == 3600
    assert s.default_max_concurrency == 3
    assert s.claude_launch_cmd == []
    assert s.codex_launch_cmd == []
    assert s.done_marker == "[ATELIER_DONE]"
    assert s.global_atelier_dir == Path.home() / ".atelier"
    # Must stay empty. A literal default would be a published shared
    # credential, and being truthy also suppresses the "serving without auth"
    # warning in `atelier serve`.
    assert s.api_token == ""


def test_env_override(tmp_path, monkeypatch):
    """Verify AtelierSettings honors ATELIER_* environment overrides.

    :param tmp_path: pytest temp directory fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setenv("ATELIER_DEFAULT_TIMEOUT", "42")
    monkeypatch.setenv(
        "ATELIER_CLAUDE_LAUNCH_CMD", '["npx","-y","custom-claude-acp"]'
    )
    monkeypatch.setenv("ATELIER_ATELIER_DIR", str(tmp_path / "somewhere"))
    monkeypatch.setenv(
        "ATELIER_GLOBAL_ATELIER_DIR", str(tmp_path / "global_here")
    )
    s = AtelierSettings(_env_file=None)
    assert s.default_timeout == 42
    assert s.claude_launch_cmd == ["npx", "-y", "custom-claude-acp"]
    assert s.atelier_dir == Path(tmp_path / "somewhere")
    assert s.global_atelier_dir == Path(tmp_path / "global_here")


def test_harnesses_env_parses_json_map(monkeypatch):
    """Verify ATELIER_HARNESSES loads as a name -> argv map.

    :param monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setenv(
        "ATELIER_HARNESSES", '{"gemini": ["npx", "-y", "gemini-acp"]}'
    )
    s = AtelierSettings(_env_file=None)
    assert s.harnesses == {"gemini": ["npx", "-y", "gemini-acp"]}


@pytest.mark.parametrize(
    "harnesses",
    [
        {"My Agent": ["a"]},  # unusable: no conduit could name it
        {"gemini": []},       # unusable: nothing to spawn
    ],
)
def test_unusable_harness_entry_is_rejected(harnesses):
    """Verify a harness entry no conduit could reference or run fails loudly.

    :param harnesses: parametrized invalid harness map under test.
    """
    with pytest.raises(ValidationError):
        AtelierSettings(_env_file=None, harnesses=harnesses)
