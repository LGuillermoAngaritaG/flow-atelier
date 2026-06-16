import { describe, it, expect } from "vitest";
import { renderConduitYaml } from "@/utils/yaml";
import type { Conduit } from "@/types/conduit";

const minimalConduit: Conduit = {
  name: "test_flow",
  description: "A test conduit",
  inputs: {},
  tasks: [],
};

const fullConduit: Conduit = {
  name: "deploy",
  description: "Deploy the service",
  timeout: 300,
  maxConcurrency: 2,
  inputs: { service: "service slug", ref: "git ref" },
  tasks: [
    {
      name: "build",
      tool: "tool:bash",
      description: "Build",
      task: "bun run build",
      dependsOn: [],
    },
    {
      name: "review",
      tool: "harness:claude-code",
      description: "Review code",
      task: "Review the diff",
      dependsOn: ["build"],
      conditionalOn: { task: "build", kind: "match", pattern: "ok" },
    },
    {
      name: "retry_step",
      tool: "tool:bash",
      description: "Retry",
      task: "run with retry",
      dependsOn: [],
      repeat: 5,
      interactive: true,
      inputs: { env: "staging" },
    },
  ],
};

describe("renderConduitYaml", () => {
  it("renders a minimal conduit with name and empty inputs/tasks", () => {
    const result = renderConduitYaml(minimalConduit);
    expect(result).toContain("name: test_flow");
    expect(result).toContain("description: \"A test conduit\"");
    expect(result).toContain("inputs:");
    expect(result).toContain("tasks:");
  });

  it("renders optional fields (timeout, maxConcurrency)", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("timeout: 300");
    expect(result).toContain("max_concurrency: 2");
  });

  it("renders conduit inputs as key-value pairs", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("  service: \"service slug\"");
    expect(result).toContain("  ref: \"git ref\"");
  });

  it("renders task name and tool", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("- name: build");
    expect(result).toContain("tool: tool:bash");
  });

  it("renders depends_on when task has dependencies", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("depends_on: [build]");
  });

  it("omits depends_on when task has no dependencies", () => {
    const result = renderConduitYaml(minimalConduit);
    expect(result).not.toContain("depends_on:");
  });

  it("renders conditional_on when present", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("conditional_on: { task: build, match: \"ok\" }");
  });

  it("renders repeat when present", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("repeat: 5");
  });

  it("renders interactive when true", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("interactive: true");
  });

  it("renders task-level inputs when present", () => {
    const result = renderConduitYaml(fullConduit);
    expect(result).toContain("env: \"staging\"");
  });
});
