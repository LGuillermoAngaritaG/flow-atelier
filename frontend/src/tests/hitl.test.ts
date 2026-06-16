import { describe, it, expect } from "vitest";
import { shouldGate, buildHitlRequest } from "@/runner/hitl";
import type { Conduit, ConduitTask } from "@/types/conduit";

const makeConduit = (name: string): Conduit => ({
  name,
  description: "test",
  inputs: {},
  tasks: [],
});

const bashTask: ConduitTask = {
  name: "build",
  tool: "tool:bash",
  description: "Build",
  task: "bun run build",
  dependsOn: [],
};

const hitlTask: ConduitTask = {
  name: "review",
  tool: "tool:hitl",
  description: "Human review",
  task: "Approve?",
  dependsOn: [],
};

describe("shouldGate", () => {
  it("returns true for tool:hitl tasks", () => {
    expect(shouldGate(makeConduit("test"), hitlTask)).toBe(true);
  });

  it("returns false for non-hitl tasks with unregistered conduit", () => {
    expect(shouldGate(makeConduit("unknown"), bashTask)).toBe(false);
  });

  it("returns false for non-hitl tasks with any conduit (empty hitlByConduitName set)", () => {
    expect(shouldGate(makeConduit("release_notes"), bashTask)).toBe(false);
  });
});

describe("buildHitlRequest", () => {
  it("returns request with fromTool matching task tool", () => {
    const req = buildHitlRequest(makeConduit("test"), hitlTask);
    expect(req.fromTool).toBe("tool:hitl");
  });

  it("returns request with empty comment", () => {
    const req = buildHitlRequest(makeConduit("test"), hitlTask);
    expect(req.comment).toBe("");
  });

  it("preserves tool type for bash tasks too", () => {
    const req = buildHitlRequest(makeConduit("test"), bashTask);
    expect(req.fromTool).toBe("tool:bash");
  });
});
