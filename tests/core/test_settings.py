"""Settings unit tests."""
from pathlib import Path

from app.core.settings import AtelierSettings


def test_defaults(tmp_path, monkeypatch):
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


def test_env_override(tmp_path, monkeypatch):
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
