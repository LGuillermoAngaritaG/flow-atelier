"""Filesystem store tests."""
import json

import pytest
import yaml

from flow_atelier.schemas.log import LogEntry
from flow_atelier.schemas.progress import FlowStatus, Progress, TaskProgress, TaskStatus
from flow_atelier.services.store.filesystem import FilesystemStore

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
    """Provide a FilesystemStore seeded with a sample hello conduit.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(
        tmp_path / ".atelier", global_dir=tmp_path / "global_atelier"
    )
    conduit_dir = s.base_dir / "conduits" / "hello"
    conduit_dir.mkdir(parents=True)
    (conduit_dir / "conduit.yaml").write_text(CONDUIT_YAML)
    return s


def test_global_conduits_dir_created_lazily(tmp_path):
    """Verify the global conduits dir is created lazily on store init.

    :param tmp_path: pytest temp directory fixture.
    """
    global_dir = tmp_path / "g_atelier"
    FilesystemStore(tmp_path / ".atelier", global_dir=global_dir)
    assert (global_dir / "conduits").is_dir()
    assert not (global_dir / "flows").exists()


def test_global_dir_none_is_allowed(tmp_path):
    """Store works without a global dir (backwards-compatible path).

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    assert s.list_conduits() == []


def test_read_conduit(store):
    """Verify read_conduit returns the parsed conduit by name.

    :param store: FilesystemStore fixture.
    """
    c = store.read_conduit("hello")
    assert c.name == "hello"
    assert c.tasks[0].name == "greet"


def test_read_conduit_malformed_yaml_raises_one_line(store):
    """Verify broken YAML raises a one-line ValueError, not a raw traceback.

    :param store: FilesystemStore fixture.
    """
    (store.base_dir / "conduits" / "hello" / "conduit.yaml").write_text(
        "name: hello\ntasks: [unclosed\n"
    )
    with pytest.raises(ValueError, match="hello: invalid YAML"):
        store.read_conduit("hello")


def test_list_conduits(store):
    """Verify list_conduits returns the names of available conduits.

    :param store: FilesystemStore fixture.
    """
    assert store.list_conduits() == ["hello"]


def test_create_flow_layout(store):
    """Verify create_flow scaffolds the expected on-disk layout.

    :param store: FilesystemStore fixture.
    """
    flow_id = store.create_flow("hello", inputs={"a": 1})
    flow_dir = store._flow_dir(flow_id)
    assert (flow_dir / "input.yaml").exists()
    assert (flow_dir / "logs.jsonl").exists()
    assert (flow_dir / "progress.json").exists()
    assert (flow_dir / "flows").is_dir()
    data = yaml.safe_load((flow_dir / "input.yaml").read_text())
    assert data == {"a": 1}


def test_list_flows(store):
    """Verify list_flows returns ids for all created flows.

    :param store: FilesystemStore fixture.
    """
    fid1 = store.create_flow("hello", {})
    fid2 = store.create_flow("hello", {})
    listed = store.list_flows()
    assert fid1 in listed and fid2 in listed


def test_nested_flow_under_parent(store):
    """Verify child flows nest under the parent flow's flows directory.

    :param store: FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    child = store.create_flow("hello", {}, parent_flow_id=parent)
    child_dir = store._flow_dir(child)
    assert child_dir.parent.name == "flows"
    assert child_dir.parent.parent == store._flow_dir(parent)


async def test_append_log_and_read(store):
    """Verify append_log appends entries and read returns them in order.

    :param store: FilesystemStore fixture.
    """
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
    logs_path = store._flow_dir(fid) / "logs.jsonl"
    logs = [json.loads(line) for line in logs_path.read_text().splitlines()]
    assert len(logs) == 2
    assert logs[0]["task"] == "greet"
    assert [e.task for e in store.read_logs(fid)] == ["greet", "greet"]


async def test_read_logs_legacy_json_fallback(store):
    """Verify read_logs falls back to a legacy logs.json array.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    flow_dir = store._flow_dir(fid)
    (flow_dir / "logs.jsonl").unlink()
    legacy = [
        LogEntry(
            task="greet",
            tool="tool:bash",
            command="echo hi",
            stdout="hi\n",
            output="hi\n",
            exit_code=0,
            started_at="2026-04-12T10:00:00Z",
            finished_at="2026-04-12T10:00:00Z",
        ).model_dump()
    ]
    (flow_dir / "logs.json").write_text(json.dumps(legacy))
    logs = store.read_logs(fid)
    assert len(logs) == 1
    assert logs[0].task == "greet"


def test_progress_roundtrip(store):
    """Verify write_progress and read_progress round-trip task state.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    p = Progress(
        status=FlowStatus.running,
        tasks={"greet": TaskProgress(status=TaskStatus.completed)},
    )
    store.write_progress(fid, p)
    restored = store.read_progress(fid)
    assert restored.tasks["greet"].status == TaskStatus.completed


def test_append_input_overwrites(store):
    """Verify append_input adds new keys and overwrites existing ones.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {"existing": "val"})
    store.append_input(fid, "new", "added")
    store.append_input(fid, "existing", "changed")
    data = store.read_input(fid)
    assert data == {"existing": "changed", "new": "added"}


def test_flow_dir_resolves_top_level_without_scan(store, monkeypatch):
    """A fresh store instance must resolve top-level flow dirs from the
    deterministic path, never via the recursive rglob fallback.

    :param store: seeded FilesystemStore fixture.
    :param monkeypatch: pytest monkeypatch fixture.
    """
    fid = store.create_flow("hello", {})
    fresh = FilesystemStore(store.base_dir)

    def _no_scan(self, pattern):
        raise AssertionError("rglob fallback must not be used for top-level flows")

    monkeypatch.setattr(type(fresh.base_dir), "rglob", _no_scan)
    assert fresh._flow_dir(fid).name == fid


def test_flow_dir_falls_back_to_scan_for_nested(store):
    """Nested child flows are still found via the recursive fallback.

    :param store: seeded FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    child = store.create_flow("hello", {}, parent_flow_id=parent)
    fresh = FilesystemStore(store.base_dir)
    assert fresh._flow_dir(child).parent.name == "flows"


def test_read_unknown_conduit_raises(store):
    """Verify read_conduit raises FileNotFoundError for unknown names.

    :param store: FilesystemStore fixture.
    """
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
    """Write a conduit YAML file under root/conduits/name/conduit.yaml.

    :param root: root directory containing the conduits folder.
    :param name: conduit directory name.
    :param yaml_text: YAML content to write.
    """
    d = root / "conduits" / name
    d.mkdir(parents=True)
    (d / "conduit.yaml").write_text(yaml_text)


def test_read_conduit_falls_back_to_global(tmp_path):
    """Verify read_conduit falls back to the global directory.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(global_dir, "deploy", GLOBAL_DEPLOY_YAML)
    c = s.read_conduit("deploy")
    assert c.name == "deploy"
    assert c.description == "Global deploy"


def test_project_conduit_shadows_global(tmp_path):
    """Verify a project-local conduit shadows a same-named global one.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(global_dir, "hello", GLOBAL_DEPLOY_YAML.replace("deploy", "hello"))
    _write_conduit(project, "hello", PROJECT_HELLO_OVERRIDE_YAML)
    c = s.read_conduit("hello")
    assert c.description == "Project-specific hello"


def test_list_conduits_unions_project_and_global(tmp_path):
    """Verify list_conduits returns the union of project and global conduits.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    _write_conduit(project, "hello", PROJECT_HELLO_OVERRIDE_YAML)
    _write_conduit(global_dir, "deploy", GLOBAL_DEPLOY_YAML)
    assert s.list_conduits() == ["deploy", "hello"]


def test_list_conduits_with_source_project_shadows_global(tmp_path):
    """Verify list_conduits_with_source reports project shadowing for duplicates.

    :param tmp_path: pytest temp directory fixture.
    """
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
    """Verify read_conduit raises when missing from both project and global.

    :param tmp_path: pytest temp directory fixture.
    """
    project = tmp_path / ".atelier"
    global_dir = tmp_path / "global_atelier"
    s = FilesystemStore(project, global_dir=global_dir)
    with pytest.raises(FileNotFoundError):
        s.read_conduit("nope")


# --------------------------------------------------------------- write/delete


from flow_atelier.schemas.conduit import Conduit


def _build_conduit(name: str, description: str = "d") -> Conduit:
    """Build a minimal Conduit fixture with a single echo task.

    :param name: conduit name.
    :param description: conduit description.
    """
    return Conduit.model_validate(
        {
            "name": name,
            "description": description,
            "tasks": [
                {
                    "name": "echo",
                    "description": "echo",
                    "task": "echo hi",
                    "tool": "tool:bash",
                    "depends_on": [],
                }
            ],
        }
    )


def test_write_conduit_creates_yaml_and_round_trips(tmp_path):
    """Verify write_conduit creates the YAML file and round-trips on read.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    c = _build_conduit("release_notes")
    s.write_conduit(c)
    assert (s.base_dir / "conduits" / "release_notes" / "conduit.yaml").exists()
    restored = s.read_conduit("release_notes")
    assert restored.name == "release_notes"
    assert restored.tasks[0].task == "echo hi"


def test_write_conduit_overwrites_existing(tmp_path):
    """Verify write_conduit overwrites an existing conduit's YAML.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    s.write_conduit(_build_conduit("x", description="old"))
    s.write_conduit(_build_conduit("x", description="new"))
    restored = s.read_conduit("x")
    assert restored.description == "new"


def test_delete_conduit_removes_directory(tmp_path):
    """Verify delete_conduit removes the conduit directory entirely.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    s.write_conduit(_build_conduit("x"))
    assert s.delete_conduit("x") is True
    assert not (s.base_dir / "conduits" / "x").exists()
    with pytest.raises(FileNotFoundError):
        s.read_conduit("x")


def test_delete_conduit_idempotent_returns_false(tmp_path):
    """Verify delete_conduit returns False when the conduit does not exist.

    :param tmp_path: pytest temp directory fixture.
    """
    s = FilesystemStore(tmp_path / ".atelier")
    assert s.delete_conduit("nope") is False


# --------------------------------------------------------------- delete_flow


def test_delete_flow_removes_dir_and_evicts_caches(store):
    """delete_flow removes the directory and evicts both in-memory caches.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    store._lock_for(fid)  # populate _log_locks for this id
    flow_dir = store._flow_dir(fid)
    assert flow_dir.exists()

    assert store.delete_flow(fid) is True
    assert not flow_dir.exists()
    assert fid not in store._flow_paths
    assert fid not in store._log_locks


def test_delete_flow_unknown_returns_false(store):
    """delete_flow returns False for an unknown flow id.

    :param store: FilesystemStore fixture.
    """
    assert store.delete_flow("20260101_deadbeef_hello") is False


def test_delete_flow_removes_nested_children(store):
    """Deleting a parent removes its nested child subtree and evicts the
    child's cached path/lock entries.

    :param store: FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    child = store.create_flow("hello", {}, parent_flow_id=parent)
    store._lock_for(child)
    child_dir = store._flow_dir(child)
    assert child_dir.exists()

    assert store.delete_flow(parent) is True
    assert not child_dir.exists()
    assert parent not in store._flow_paths
    assert child not in store._flow_paths
    assert child not in store._log_locks


def test_read_logs_warns_on_corrupt_interior_line(store, caplog):
    """A corrupt interior log line is dropped with a warning, not silently.

    :param store: FilesystemStore fixture.
    :param caplog: pytest log-capture fixture.
    """
    fid = store.create_flow("hello", {})
    good = LogEntry(
        task="greet", tool="tool:bash", command="echo hi",
        output="hi", exit_code=0,
        started_at="2026-04-12T10:00:00Z", finished_at="2026-04-12T10:00:00Z",
    )
    line = good.model_dump_json()
    logs_path = store._flow_dir(fid) / "logs.jsonl"
    logs_path.write_text(f"{line}\n{{not json\n{line}\n")
    with caplog.at_level("WARNING"):
        entries = store.read_logs(fid)
    assert [e.task for e in entries] == ["greet", "greet"]
    assert any("unreadable line" in r.message for r in caplog.records)


def test_read_logs_silent_on_truncated_trailing_line(store, caplog):
    """A truncated trailing line (crash mid-write) is dropped without warning.

    :param store: FilesystemStore fixture.
    :param caplog: pytest log-capture fixture.
    """
    fid = store.create_flow("hello", {})
    good = LogEntry(
        task="greet", tool="tool:bash", command="echo hi",
        output="hi", exit_code=0,
        started_at="2026-04-12T10:00:00Z", finished_at="2026-04-12T10:00:00Z",
    )
    line = good.model_dump_json()
    logs_path = store._flow_dir(fid) / "logs.jsonl"
    logs_path.write_text(f"{line}\n{{truncat")
    with caplog.at_level("WARNING"):
        entries = store.read_logs(fid)
    assert [e.task for e in entries] == ["greet"]
    assert not any("unreadable line" in r.message for r in caplog.records)
