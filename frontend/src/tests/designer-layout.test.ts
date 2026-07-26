import { describe, it, expect } from "vitest";
import { layerTasks, layoutPositions } from "@/features/designer/layout";
import type { ConduitTask } from "@/types/conduit";

function task(name: string, dependsOn: string[] = []): ConduitTask {
  return {
    name,
    tool: "tool:bash",
    description: name,
    task: `echo ${name}`,
    dependsOn,
  };
}

describe("layerTasks", () => {
  it("puts a linear chain in consecutive columns", () => {
    const depth = layerTasks([task("a"), task("b", ["a"]), task("c", ["b"])]);
    expect([depth.get("a"), depth.get("b"), depth.get("c")]).toEqual([0, 1, 2]);
  });

  it("puts siblings sharing a dependency in the same column", () => {
    const depth = layerTasks([
      task("clone"),
      task("tests", ["clone"]),
      task("review", ["clone"]),
    ]);
    expect(depth.get("tests")).toBe(1);
    expect(depth.get("review")).toBe(1);
  });

  it("uses the longest path when a task has dependencies of differing depth", () => {
    // approve depends on both clone (depth 0) and tests (depth 1), so it must
    // land right of tests, not right of clone.
    const depth = layerTasks([
      task("clone"),
      task("tests", ["clone"]),
      task("approve", ["clone", "tests"]),
    ]);
    expect(depth.get("approve")).toBe(2);
  });

  it("does not hang on a dependency cycle", () => {
    const depth = layerTasks([task("a", ["b"]), task("b", ["a"])]);
    expect(depth.size).toBe(2);
  });

  it("ignores dependency names that do not exist", () => {
    const depth = layerTasks([task("a", ["ghost"])]);
    expect(depth.get("a")).toBe(0);
  });

  it("ignores a self-dependency", () => {
    const depth = layerTasks([task("a", ["a"])]);
    expect(depth.get("a")).toBe(0);
  });
});

describe("layoutPositions", () => {
  it("stacks same-column tasks into separate rows", () => {
    const pos = layoutPositions(
      [task("clone"), task("tests", ["clone"]), task("review", ["clone"])],
      100,
      50,
      0,
    );
    expect(pos.get("clone")).toEqual({ x: 0, y: 0 });
    expect(pos.get("tests")).toEqual({ x: 100, y: 0 });
    expect(pos.get("review")).toEqual({ x: 100, y: 50 });
  });
});
