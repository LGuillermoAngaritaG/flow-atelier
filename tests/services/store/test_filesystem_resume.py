"""Tests for new store methods: list_child_flows, read_outputs, create_flow(flow_id=...)."""
from __future__ import annotations

import pytest

from flow_atelier.schemas.flow import new_flow_id
from flow_atelier.services.store.filesystem import FilesystemStore


@pytest.fixture
def store(tmp_path):
    """Provide a FilesystemStore rooted under the pytest temp path.

    :param tmp_path: pytest temp directory fixture.
    """
    return FilesystemStore(tmp_path / ".atelier")


# ---------------------------------------------------------------- list_child_flows


def test_list_child_flows_empty(store):
    """Verify list_child_flows returns an empty list when there are no children.

    :param store: FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    assert store.list_child_flows(parent) == []


def test_list_child_flows_returns_children(store):
    """Verify list_child_flows returns child flow ids sorted.

    :param store: FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    child_a = store.create_flow("hello", {}, parent_flow_id=parent)
    child_b = store.create_flow("hello", {}, parent_flow_id=parent)
    children = store.list_child_flows(parent)
    assert sorted([child_a, child_b]) == children


def test_list_child_flows_excludes_parent(store):
    """Verify list_child_flows does not include the parent itself.

    :param store: FilesystemStore fixture.
    """
    parent = store.create_flow("hello", {})
    store.create_flow("hello", {}, parent_flow_id=parent)
    assert parent not in store.list_child_flows(parent)


# ---------------------------------------------------------------- read_outputs


def test_read_outputs_missing_returns_empty(store):
    """Verify read_outputs returns an empty dict when outputs.yaml does not exist.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    assert store.read_outputs(fid) == {}


def test_read_outputs_round_trips(store):
    """Verify write_outputs and read_outputs round-trip a task map.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    store.write_outputs(fid, {"greet": "hi", "build": "ok"})
    assert store.read_outputs(fid) == {"greet": "hi", "build": "ok"}


def test_read_outputs_overwrites(store):
    """Verify write_outputs overwrites the previous file.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    store.write_outputs(fid, {"a": "1"})
    store.write_outputs(fid, {"b": "2"})
    assert store.read_outputs(fid) == {"b": "2"}


# ---------------------------------------------------------------- create_flow(flow_id=...)


def test_create_flow_with_explicit_flow_id(store):
    """Verify create_flow uses the provided flow_id instead of generating one.

    :param store: FilesystemStore fixture.
    """
    explicit = new_flow_id("custom")
    fid = store.create_flow("custom", {}, flow_id=explicit)
    assert fid == explicit


def test_create_flow_without_flow_id_generates_one(store):
    """Verify create_flow generates a flow_id when none is provided.

    :param store: FilesystemStore fixture.
    """
    fid = store.create_flow("hello", {})
    assert "hello" in fid


def test_create_flow_with_explicit_flow_id_persists(store):
    """Verify the flow directory is created with the explicit flow_id.

    :param store: FilesystemStore fixture.
    """
    explicit = new_flow_id("custom")
    store.create_flow("custom", {"x": 1}, flow_id=explicit)
    flow_dir = store._flow_dir(explicit)
    assert flow_dir.exists()
    assert (flow_dir / "input.yaml").exists()
