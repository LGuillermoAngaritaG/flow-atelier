import { describe, it, expect } from "vitest";
import {
  reducer,
  isMockEntry,
  backendLogToLines,
  taskToLine,
  mapStepStatus,
} from "@/hooks/useConduit";
import type { State, LiveRunStatus } from "@/hooks/useConduit";
import type { BackendLogEntry, BackendTask } from "@/types/ws";
import type { LogEntry, FlowTaskStatus } from "@/types/task";

// ── Helpers ────────────────────────────────────────────────────────────────

const freshState = (): State => ({ runs: new Map() });

const run = (flowId: string, overrides: Partial<{ conduitName: string; status: string }> = {}) => ({
  flowId,
  conduitName: overrides.conduitName ?? "test-conduit",
  startedAt: Date.now(),
  status: (overrides.status ?? "running") as LiveRunStatus,
  logLines: [] as LogEntry[],
  taskStatuses: {} as Record<string, FlowTaskStatus>,
  runPath: "/test",
  inputs: {} as Record<string, string>,
});

const makeBackendLog = (overrides: Partial<BackendLogEntry> = {}): BackendLogEntry => ({
  task: "build",
  tool: "tool:bash",
  iteration: 1,
  of: 1,
  command: "",
  stdout: "",
  stderr: "",
  exitCode: 0,
  output: "",
  startedAt: "2026-04-15T18:00:00Z",
  finishedAt: "2026-04-15T18:00:01Z",
  durationSeconds: 1,
  extra: {},
  tasks: [],
  ...overrides,
});

// ── mapStepStatus ──────────────────────────────────────────────────────────

describe("mapStepStatus", () => {
  it('maps "completed" to "done"', () => {
    expect(mapStepStatus("completed")).toBe("done");
  });

  it('maps "cancelled" to "failed"', () => {
    expect(mapStepStatus("cancelled")).toBe("failed");
  });

  it("passes through other statuses", () => {
    expect(mapStepStatus("running")).toBe("running");
    expect(mapStepStatus("pending")).toBe("pending");
  });
});

// ── isMockEntry ────────────────────────────────────────────────────────────

describe("isMockEntry", () => {
  it("returns true for a frontend LogEntry", () => {
    expect(isMockEntry({ t: 0, text: "hi", level: "info" })).toBe(true);
  });

  it("returns false for a backend BackendLogEntry", () => {
    expect(isMockEntry(makeBackendLog())).toBe(false);
  });
});

// ── backendLogToLines ──────────────────────────────────────────────────────

describe("backendLogToLines", () => {
  it("returns ok level for exitCode 0", () => {
    const lines = backendLogToLines(makeBackendLog({ stdout: "ok" }));
    expect(lines.every((l) => l.level === "ok")).toBe(true);
  });

  it("returns err level for non-zero exitCode", () => {
    const lines = backendLogToLines(makeBackendLog({ exitCode: 1, stderr: "fail" }));
    expect(lines.some((l) => l.level === "err")).toBe(true);
  });

  it("prefixes command with $", () => {
    const lines = backendLogToLines(makeBackendLog({ command: "npm test" }));
    expect(lines[0].text).toBe("$ npm test");
    expect(lines[0].level).toBe("info");
  });

  it("splits multiline stdout, trims, and filters empty", () => {
    const lines = backendLogToLines(makeBackendLog({ stdout: "line1\n\nline2\n" }));
    const texts = lines.map((l) => l.text);
    expect(texts).toContain("line1");
    expect(texts).toContain("line2");
    expect(texts).not.toContain("");
  });

  it("marks stderr lines as err", () => {
    const lines = backendLogToLines(makeBackendLog({ exitCode: 1, stderr: "oops" }));
    const errLine = lines.find((l) => l.text === "oops");
    expect(errLine?.level).toBe("err");
  });

  it("includes output when different from stdout", () => {
    const lines = backendLogToLines(makeBackendLog({ stdout: "out", output: "summary" }));
    const texts = lines.map((l) => l.text);
    expect(texts).toContain("summary");
  });
});

// ── taskToLine ─────────────────────────────────────────────────────────────

describe("taskToLine", () => {
  it("returns info LogEntry for thinking with text", () => {
    const line = taskToLine({
      kind: "thinking",
      timestamp: "2026-04-15T18:00:00Z",
      text: "pondering",
      toolCallId: "",
      toolName: "",
      toolKind: "",
      toolStatus: "",
      toolInput: "",
      toolOutput: "",
      locations: [],
    } satisfies BackendTask);
    expect(line).not.toBeNull();
    expect(line!.level).toBe("info");
    expect(line!.text).toBe("pondering");
  });

  it("returns null for thinking with empty text", () => {
    const line = taskToLine({
      kind: "thinking",
      timestamp: "2026-04-15T18:00:00Z",
      text: "",
      toolCallId: "",
      toolName: "",
      toolKind: "",
      toolStatus: "",
      toolInput: "",
      toolOutput: "",
      locations: [],
    } satisfies BackendTask);
    expect(line).toBeNull();
  });

  it("returns acc LogEntry for tool_call", () => {
    const line = taskToLine({
      kind: "tool_call",
      timestamp: "2026-04-15T18:00:00Z",
      text: "",
      toolCallId: "1",
      toolName: "read_file",
      toolKind: "",
      toolStatus: "",
      toolInput: "",
      toolOutput: "",
      locations: [],
    } satisfies BackendTask);
    expect(line).not.toBeNull();
    expect(line!.text).toBe("→ read_file");
    expect(line!.level).toBe("acc");
  });

  it("returns err level for tool_result with error status", () => {
    const line = taskToLine({
      kind: "tool_result",
      timestamp: "2026-04-15T18:00:00Z",
      text: "",
      toolCallId: "1",
      toolName: "",
      toolKind: "",
      toolStatus: "error",
      toolInput: "",
      toolOutput: "file not found",
      locations: [],
    } satisfies BackendTask);
    expect(line!.level).toBe("err");
  });

  it("returns ok level for tool_result with success status", () => {
    const line = taskToLine({
      kind: "tool_result",
      timestamp: "2026-04-15T18:00:00Z",
      text: "",
      toolCallId: "1",
      toolName: "",
      toolKind: "",
      toolStatus: "success",
      toolInput: "",
      toolOutput: "done",
      locations: [],
    } satisfies BackendTask);
    expect(line!.level).toBe("ok");
  });

  it("returns null for tool_result with empty output and status", () => {
    const line = taskToLine({
      kind: "tool_result",
      timestamp: "2026-04-15T18:00:00Z",
      text: "",
      toolCallId: "1",
      toolName: "",
      toolKind: "",
      toolStatus: "",
      toolInput: "",
      toolOutput: "",
      locations: [],
    } satisfies BackendTask);
    expect(line).toBeNull();
  });
});

// ── reducer ────────────────────────────────────────────────────────────────

describe("reducer", () => {
  it("returns same state for unknown flowId on WS_STEP", () => {
    const state = freshState();
    const next = reducer(state, {
      type: "WS_STEP",
      flowId: "nope",
      line: { t: 0, text: "hi", level: "info" },
    });
    expect(next.runs.size).toBe(0);
  });

  describe("WS_STARTED", () => {
    it("creates a fresh run", () => {
      const state = freshState();
      const next = reducer(state, {
        type: "WS_STARTED",
        flowId: "f1",
        conduitName: "deploy",
        runPath: "/tmp",
        inputs: { ref: "main" },
      });
      const r = next.runs.get("f1")!;
      expect(r).toBeDefined();
      expect(r.conduitName).toBe("deploy");
      expect(r.status).toBe("running");
      expect(r.runPath).toBe("/tmp");
      expect(r.inputs).toEqual({ ref: "main" });
      expect(r.logLines.length).toBeGreaterThan(0);
    });

    it("appends resumed marker when run already exists", () => {
      const state = freshState();
      state.runs.set("f1", {
        flowId: "f1",
        conduitName: "deploy",
        startedAt: Date.now(),
        status: "running",
        logLines: [],
        taskStatuses: {},
        runPath: "/tmp",
        inputs: {},
      });
      const next = reducer(state, {
        type: "WS_STARTED",
        flowId: "f1",
        conduitName: "deploy",
        runPath: "/tmp",
        inputs: {},
      });
      const r = next.runs.get("f1")!;
      expect(r.logLines.length).toBe(1);
      expect(r.logLines[0].text).toContain("resumed");
    });

    it("creates child flow with parent reference", () => {
      const state = freshState();
      // Parent must exist first
      state.runs.set("parent1", {
        flowId: "parent1",
        conduitName: "main",
        startedAt: Date.now(),
        status: "running",
        logLines: [],
        taskStatuses: {},
        runPath: "",
        inputs: {},
      });
      const next = reducer(state, {
        type: "WS_STARTED",
        flowId: "child1",
        conduitName: "sub",
        runPath: "",
        inputs: {},
        parentFlowId: "parent1",
        parentTask: "step1",
      });
      const child = next.runs.get("child1")!;
      expect(child.parentFlowId).toBe("parent1");
      expect(child.parentTask).toBe("step1");
      // Parent gets a marker
      const parent = next.runs.get("parent1")!;
      expect(parent.logLines.length).toBe(1);
      expect(parent.logLines[0].text).toContain("sub-conduit started");
    });
  });

  describe("WS_STEP", () => {
    it("appends a log line", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const line: LogEntry = { t: 1, text: "step output", level: "info" };
      const next = reducer(state, { type: "WS_STEP", flowId: "f1", line });
      expect(next.runs.get("f1")!.logLines).toHaveLength(1);
    });
  });

  describe("WS_LOG", () => {
    it("appends multiple log lines", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const lines: LogEntry[] = [
        { t: 1, text: "a", level: "info" },
        { t: 2, text: "b", level: "ok" },
      ];
      const next = reducer(state, { type: "WS_LOG", flowId: "f1", lines });
      expect(next.runs.get("f1")!.logLines).toHaveLength(2);
    });
  });

  describe("WS_STEP_STATUS", () => {
    it("updates taskStatuses and appends marker", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const marker: LogEntry = { t: 1, text: "▸ build", level: "info", task: "build" };
      const next = reducer(state, {
        type: "WS_STEP_STATUS",
        flowId: "f1",
        step: "build",
        status: "running",
        marker,
      });
      const r = next.runs.get("f1")!;
      expect(r.taskStatuses["build"]).toBe("running");
      expect(r.logLines).toHaveLength(1);
    });

    it("updates taskStatuses without marker", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const next = reducer(state, {
        type: "WS_STEP_STATUS",
        flowId: "f1",
        step: "build",
        status: "done",
      });
      expect(next.runs.get("f1")!.taskStatuses["build"]).toBe("done");
      expect(next.runs.get("f1")!.logLines).toHaveLength(0);
    });
  });

  describe("WS_HITL_REQUEST", () => {
    it("sets hitlRequest with comment from last log line", () => {
      const state = freshState();
      state.runs.set("f1", {
        ...run("f1"),
        logLines: [{ t: 1, text: "needs approval", level: "acc" }],
      });
      const next = reducer(state, {
        type: "WS_HITL_REQUEST",
        flowId: "f1",
        inputs: [{ name: "approve", description: "Yes/No" }],
        taskName: "review",
      });
      const r = next.runs.get("f1")!;
      expect(r.hitlRequest).toBeDefined();
      expect(r.hitlRequest!.comment).toBe("needs approval");
      expect(r.hitlRequest!.taskName).toBe("review");
      expect(r.hitlRequest!.inputs).toEqual([{ name: "approve", description: "Yes/No" }]);
    });
  });

  describe("WS_FLOW_COMPLETE", () => {
    it("sets status to done with completion log", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const next = reducer(state, { type: "WS_FLOW_COMPLETE", flowId: "f1" });
      const r = next.runs.get("f1")!;
      expect(r.status).toBe("done");
      const lastLog = r.logLines[r.logLines.length - 1];
      expect(lastLog.text).toContain("complete");
      expect(lastLog.level).toBe("ok");
    });
  });

  describe("WS_FLOW_FAILED", () => {
    it("sets status to failed with error log", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const next = reducer(state, { type: "WS_FLOW_FAILED", flowId: "f1", error: "boom" });
      const r = next.runs.get("f1")!;
      expect(r.status).toBe("failed");
      expect(r.logLines[r.logLines.length - 1].text).toContain("boom");
      expect(r.logLines[r.logLines.length - 1].level).toBe("err");
    });

    it("preserves cancelled status when already cancelled", () => {
      const state = freshState();
      state.runs.set("f1", { ...run("f1"), status: "cancelled" });
      const next = reducer(state, { type: "WS_FLOW_FAILED", flowId: "f1", error: "boom" });
      expect(next.runs.get("f1")!.status).toBe("cancelled");
    });
  });

  describe("CANCEL", () => {
    it("sets status to cancelled when running", () => {
      const state = freshState();
      state.runs.set("f1", run("f1"));
      const next = reducer(state, { type: "CANCEL", flowId: "f1" });
      expect(next.runs.get("f1")!.status).toBe("cancelled");
    });

    it("is no-op when run is done", () => {
      const state = freshState();
      state.runs.set("f1", { ...run("f1"), status: "done" });
      const next = reducer(state, { type: "CANCEL", flowId: "f1" });
      expect(next.runs.get("f1")!.status).toBe("done");
    });
  });

  describe("RESUME", () => {
    it("resets existing run to running and clears HITL", () => {
      const state = freshState();
      state.runs.set("f1", {
        ...run("f1"),
        status: "cancelled",
        hitlRequest: { fromTool: "tool:hitl", comment: "" },
        hitlAnswers: { q: "a" },
      });
      const next = reducer(state, { type: "RESUME", flowId: "f1" });
      const r = next.runs.get("f1")!;
      expect(r.status).toBe("running");
      expect(r.hitlRequest).toBeUndefined();
      expect(r.hitlAnswers).toBeUndefined();
    });

    it("creates a new run when flowId is unknown", () => {
      const state = freshState();
      const next = reducer(state, { type: "RESUME", flowId: "f2", conduitName: "deploy" });
      const r = next.runs.get("f2")!;
      expect(r).toBeDefined();
      expect(r.conduitName).toBe("deploy");
      expect(r.status).toBe("running");
    });
  });

  describe("ANSWER_HITL", () => {
    it("sets hitlAnswers and clears hitlRequest", () => {
      const state = freshState();
      state.runs.set("f1", {
        ...run("f1"),
        hitlRequest: { fromTool: "tool:hitl", comment: "" },
      });
      const next = reducer(state, {
        type: "ANSWER_HITL",
        flowId: "f1",
        answers: { approve: "yes" },
      });
      const r = next.runs.get("f1")!;
      expect(r.hitlAnswers).toEqual({ approve: "yes" });
      expect(r.hitlRequest).toBeUndefined();
    });
  });
});
