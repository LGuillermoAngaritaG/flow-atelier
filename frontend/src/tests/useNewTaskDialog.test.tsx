// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

const STABLE_CTX = { conduits: [], loading: false, error: null, refresh: () => {} };
vi.mock("@/services/ConduitProvider", () => ({
  useConduits: () => STABLE_CTX,
  getConduitSync: () => undefined,
}));

import { useNewTaskDialog } from "@/features/kanban/components/useNewTaskDialog";
import { useTaskStore } from "@/runner";

beforeEach(() => {
  useTaskStore.getState().setTasks([]);
});

afterEach(() => {
  useTaskStore.getState().setTasks([]);
});

function setup() {
  const onOpenChange = vi.fn();
  const view = renderHook(() =>
    useNewTaskDialog({ open: true, onOpenChange, projectId: "p1" }),
  );
  return view;
}

describe("useNewTaskDialog edit-node", () => {
  it("editing a node updates it in place without spawning a duplicate", () => {
    const { result } = setup();

    // add a node
    act(() => result.current.openNodeForm("tool:bash"));
    act(() => result.current.setNodeForm({ name: "step_one", description: "first", task: "echo 1", runPath: "" }));
    act(() => result.current.saveNode());

    expect(useTaskStore.getState().tasks).toHaveLength(1);
    expect(result.current.nodes).toHaveLength(1);

    // edit that node (same name, new description)
    act(() => result.current.editNode(0));
    act(() => result.current.setNodeForm({ name: "step_one", description: "edited", task: "echo 2", runPath: "" }));
    act(() => result.current.saveNode());

    // no duplicate: still one store task, one node
    expect(useTaskStore.getState().tasks).toHaveLength(1);
    expect(result.current.nodes).toHaveLength(1);
    expect(useTaskStore.getState().tasks[0].description).toBe("edited");
    expect(result.current.nodes[0].description).toBe("edited");
  });

  it("renaming a node on edit drops the stale backing task", () => {
    const { result } = setup();

    act(() => result.current.openNodeForm("tool:bash"));
    act(() => result.current.setNodeForm({ name: "old_name", description: "d", task: "", runPath: "" }));
    act(() => result.current.saveNode());

    act(() => result.current.editNode(0));
    act(() => result.current.setNodeForm({ name: "new_name", description: "d", task: "", runPath: "" }));
    act(() => result.current.saveNode());

    const names = useTaskStore.getState().tasks.map((t) => t.name);
    expect(names).toEqual(["new_name"]);
    expect(result.current.nodes).toHaveLength(1);
    expect(result.current.nodes[0].name).toBe("new_name");
  });
});
