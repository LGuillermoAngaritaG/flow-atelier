"""Filesystem store tests."""
import json

import pytest
import yaml

from app.schemas.log import LogEntry
from app.schemas.progress import FlowStatus, Progress, TaskProgress, TaskStatus
from app.services.store.filesystem import FilesystemStore


CONDUIT_YAML = """
name: hello
description: Say hello
tasks:
  - greet:
      description: greet
      task: "echo hi"
      tool: tool:bash
      depends_on: []
"""


@pytest.fixture
def store(tmp_path):
    s = FilesystemStore(
        tmp_path / ".atelier", global_dir=tmp_path / "global_atelier"
    )
    conduit_dir = s.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(CONDUIT_YAML)
    return s


def test_global_conduits_dir_created_lazily(tmp_path):
    global_dir = tmp_path / "g_atelier"
    FilesystemStore(tmp_path / ".atelier", global_dir=global_dir)
    assert (global_dir / "conduits").is_dir()
    assert not (global_dir / "flows").exists()


def test_global_dir_none_is_allowed(tmp_path):
    """Store works without a global dir (backwards-compatible path)."""
    s = FilesystemStore(tmp_path / ".atelier")
    assert s.list_conduits() == []


def test_read_conduit(store):
    c = store.read_conduit("hello")
    assert c.name == "hello"
    assert c.tasks[0].name == "greet"


def test_list_conduits(store):
    assert store.list_conduits() == ["hello"]


def test_create_flow_layout(store):
    flow_id = store.create_flow("hello", inputs={"a": 1})
    flow_dir = store._flow_dir(flow_id)
    assert (flow_dir / "input.yaml").exists()
    assert (flow_dir / "logs.json").exists()
    assert (flow_dir / "progress.json").exists()
    assert (flow_dir / "flows").is_dir()
    data = yaml.safe_load((flow_dir / "input.yaml").read_text())
    assert data == {"a": 1}


def test_list_flows(store):
    fid1 = store.create_flow("hello", {})
    fid2 = store.create_flow("hello", {})
    listed = store.list_flows()
    assert fid1 in listed and fid2 in listed


def test_nested_flow_under_parent(store):
    parent = store.create_flow("hello", {})
    child = store.create_flow("hello", {}, parent_flow_id=parent)
    child_dir = store._flow_dir(child)
    assert child_dir.parent.name == "flows"
    assert child_dir.parent.parent == store._flow_dir(parent)


async def test_append_log_and_read(store):
    fid = store.create_flow("hello", {})
    e1 = LogEntry(
        task="greet",
        tool="tool:bash",
        command="echo hi",
        stdout="hi\n",
        output="hi\n",
        exit_code=0,
        started_at="2026-04-12T10:00:00Z",
        finished_at="2026-04-12T10:00:00Z",
    )
    await store.append_log(fid, e1)
    await store.append_log(fid, e1)
    logs_path = store._flow_dir(fid) / "logs.json"
    logs = json.loads(logs_path.read_text())
    assert len(logs) == 2
    assert logs[0]["task"] == "greet"


def test_progress_roundtrip(store):
    fid = store.create_flow("hello", {})
    p = Progress(
        status=FlowStatus.running,
        tasks={"greet": TaskProgress(status=TaskStatus.completed)},
    )
    store.write_progress(fid, p)
    restored = store.read_progress(fid)
    assert restored.tasks["greet"].status == TaskStatus.completed


def test_append_input_overwrites(store):
    fid = store.create_flow("hello", {"existing": "val"})
    store.append_input(fid, "new", "added")
    store.append_input(fid, "existing", "changed")
    data = store.read_input(fid)
    assert data == {"existing": "changed", "new": "added"}


def test_read_unknown_conduit_raises(store):
    with pytest.raises(FileNotFoundError):
        store.read_conduit("nonexistent")


GLOBAL_DEPLOY_YAML = """
name: deploy
description: Global deploy
tasks:
  - step:
      description: step
      task: "echo deploying"
      tool: tool:bash
      depends_on: []
"""

PROJECT_HELLO_OVERRIDE_YAML = """
name: hello
description: Project-specific hello
tasks:
  - greet:
      description: local
      task: "echo local"
      tool: tool:bash
      depends_on: []
"""


def _write_conduit(root, name, yaml_text):
    d = root / "conduits" / name
    d.mkdir(parents=True)
    (d / "conduit.yaml").write_text(yaml_text)


def test_read_conduit_falls_back_to_global(tmp_path):
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(global_dir, "deploy", GLOBAL_DEPLOY_YAML)
    c = s.read_conduit("deploy")
    assert c.name == "deploy"
    assert c.description == "Global deploy"


def test_project_conduit_shadows_global(tmp_path):
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(global_dir, "hello", GLOBAL_DEPLOY_YAML.replace("deploy", "hello"))
    _write_conduit(project, "hello", PROJECT_HELLO_OVERRIDE_YAML)
    c = s.read_conduit("hello")
    assert c.description == "Project-specific hello"


def test_list_conduits_unions_project_and_global(tmp_path):
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(project, "hello", PROJECT_HELLO_OVERRIDE_YAML)
    _write_conduit(global_dir, "deploy", GLOBAL_DEPLOY_YAML)
    assert s.list_conduits() == ["deploy", "hello"]


def test_list_conduits_with_source_project_shadows_global(tmp_path):
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(
        global_dir, "hello", GLOBAL_DEPLOY_YAML.replace("deploy", "hello")
    )
    _write_conduit(global_dir, "deploy", GLOBAL_DEPLOY_YAML)
    _write_conduit(project, "hello", PROJECT_HELLO_OVERRIDE_YAML)
    entries = s.list_conduits_with_source()
    as_dict = dict(entries)
    assert as_dict == {"hello": "project", "deploy": "global"}


def test_read_missing_from_both_raises(tmp_path):
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    with pytest.raises(FileNotFoundError):
        s.read_conduit("nope")
