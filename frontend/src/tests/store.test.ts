// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import {
  useTaskStore,
  selectRunningCount,
  selectByColumn,
  selectByName,
} from "@/runner/store";
import type { Task } from "@/types/task";

const makeTask = (overrides: Partial<Task> = {}): Task => ({
  name: "test-task",
  projectId: "proj-1",
  inputs: {},
  createdAt: Date.now(),
  column: "todo",
  ...overrides,
});

afterEach(() => {
  useTaskStore.setState({ tasks: [] });
  localStorage.clear();
});

describe("useTaskStore", () => {
  describe("setTasks", () => {
    it("replaces the tasks array", () => {
      const t = makeTask({ name: "a" });
      useTaskStore.getState().setTasks([t]);
      expect(useTaskStore.getState().tasks).toEqual([t]);
    });
  });

  describe("updateTask", () => {
    it("patches the named task", () => {
      const a = makeTask({ name: "a", column: "todo" });
      const b = makeTask({ name: "b", column: "todo" });
      useTaskStore.getState().setTasks([a, b]);
      useTaskStore.getState().updateTask("a", (t) => ({ ...t, column: "done" }));
      const tasks = useTaskStore.getState().tasks;
      expect(tasks[0].column).toBe("done");
      expect(tasks[1].column).toBe("todo");
    });

    it("is a no-op for unknown name", () => {
      const a = makeTask({ name: "a" });
      useTaskStore.getState().setTasks([a]);
      useTaskStore.getState().updateTask("nonexistent", (t) => t);
      expect(useTaskStore.getState().tasks).toEqual([a]);
    });
  });

  describe("upsert", () => {
    it("prepends a new task", () => {
      const a = makeTask({ name: "a" });
      useTaskStore.getState().setTasks([a]);
      const b = makeTask({ name: "b" });
      useTaskStore.getState().upsert(b);
      const tasks = useTaskStore.getState().tasks;
      expect(tasks.map((t) => t.name)).toEqual(["b", "a"]);
    });

    it("replaces an existing task in-place", () => {
      const a = makeTask({ name: "a", column: "todo" });
      useTaskStore.getState().setTasks([a]);
      const updated = makeTask({ name: "a", column: "done" });
      useTaskStore.getState().upsert(updated);
      const tasks = useTaskStore.getState().tasks;
      expect(tasks).toHaveLength(1);
      expect(tasks[0].column).toBe("done");
    });
  });

  describe("remove", () => {
    it("removes a task by name", () => {
      const a = makeTask({ name: "a" });
      const b = makeTask({ name: "b" });
      useTaskStore.getState().setTasks([a, b]);
      useTaskStore.getState().remove("a");
      expect(useTaskStore.getState().tasks.map((t) => t.name)).toEqual(["b"]);
    });

    it("is a no-op for unknown name", () => {
      const a = makeTask({ name: "a" });
      useTaskStore.getState().setTasks([a]);
      useTaskStore.getState().remove("nonexistent");
      expect(useTaskStore.getState().tasks).toEqual([a]);
    });
  });

  describe("selectRunningCount", () => {
    it("returns 0 when no tasks are in_progress", () => {
      useTaskStore.getState().setTasks([
        makeTask({ name: "a", column: "todo" }),
        makeTask({ name: "b", column: "done" }),
      ]);
      expect(selectRunningCount(useTaskStore.getState())).toBe(0);
    });

    it("counts in_progress tasks", () => {
      useTaskStore.getState().setTasks([
        makeTask({ name: "a", column: "in_progress" }),
        makeTask({ name: "b", column: "in_progress" }),
        makeTask({ name: "c", column: "in_progress" }),
      ]);
      expect(selectRunningCount(useTaskStore.getState())).toBe(3);
    });
  });

  describe("selectByColumn", () => {
    it("filters tasks by column", () => {
      useTaskStore.getState().setTasks([
        makeTask({ name: "a", column: "todo" }),
        makeTask({ name: "b", column: "in_progress" }),
        makeTask({ name: "c", column: "todo" }),
      ]);
      const todos = selectByColumn("todo")(useTaskStore.getState());
      expect(todos.map((t) => t.name)).toEqual(["a", "c"]);
    });

    it("returns empty array for column with no tasks", () => {
      useTaskStore.getState().setTasks([
        makeTask({ name: "a", column: "todo" }),
      ]);
      expect(selectByColumn("done")(useTaskStore.getState())).toEqual([]);
    });
  });

  describe("selectByName", () => {
    it("finds a task by name", () => {
      const a = makeTask({ name: "a" });
      useTaskStore.getState().setTasks([a]);
      expect(selectByName("a")(useTaskStore.getState())).toEqual(a);
    });

    it("returns undefined for unknown name", () => {
      useTaskStore.getState().setTasks([makeTask({ name: "a" })]);
      expect(selectByName("nope")(useTaskStore.getState())).toBeUndefined();
    });
  });
});
