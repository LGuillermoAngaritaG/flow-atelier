import { describe, it, expect } from "vitest";
import { toFrontendLogEntry } from "@/services/api/run-task";

describe("toFrontendLogEntry", () => {
  it("joins command, stdout, stderr with newlines", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "npm test",
      stdout: "all pass",
      stderr: "",
      exitCode: 0,
    });
    expect(entry.text).toBe("npm test\nall pass");
    expect(entry.level).toBe("info");
  });

  it("returns level 'err' when exitCode is non-zero", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "npm test",
      stdout: "",
      stderr: "Error: failed",
      exitCode: 1,
    });
    expect(entry.level).toBe("err");
  });

  it("filters out empty strings", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "",
      stdout: "output",
      stderr: "",
      exitCode: 0,
    });
    expect(entry.text).toBe("output");
  });

  it("handles entry with only command", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "echo hello",
      stdout: "",
      stderr: "",
      exitCode: 0,
    });
    expect(entry.text).toBe("echo hello");
  });

  it("handles entry with all fields populated", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "run",
      stdout: "out",
      stderr: "err",
      exitCode: 0,
    });
    expect(entry.text).toBe("run\nout\nerr");
  });

  it("includes a timestamp", () => {
    const entry = toFrontendLogEntry({
      task: "build",
      tool: "tool:bash",
      iteration: 1,
      of: 1,
      command: "run",
      stdout: "",
      stderr: "",
      exitCode: 0,
    });
    expect(typeof entry.t).toBe("number");
    expect(entry.t).toBeGreaterThan(0);
  });
});
