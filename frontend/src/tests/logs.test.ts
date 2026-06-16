import { describe, it, expect } from "vitest";
import { mockGetFlowLogs } from "@/services/mock/logs";

describe("mockGetFlowLogs", () => {
  const knownFlowId = "a1b2c3d4-5678-4abc-9def-0012048abcde";

  it("returns non-empty array for known flowId", () => {
    const logs = mockGetFlowLogs(knownFlowId);
    expect(logs.length).toBeGreaterThan(0);
  });

  it("returns empty array for unknown flowId", () => {
    expect(mockGetFlowLogs("nonexistent-id")).toEqual([]);
  });

  it("returns entries with valid LogEntry shape", () => {
    const logs = mockGetFlowLogs(knownFlowId);
    const validLevels = new Set(["info", "ok", "err", "acc"]);
    for (const entry of logs) {
      expect(typeof entry.t).toBe("number");
      expect(entry.t).toBeGreaterThan(0);
      expect(typeof entry.text).toBe("string");
      expect(validLevels.has(entry.level)).toBe(true);
    }
  });

  it("returns entries ordered by timestamp ascending", () => {
    const logs = mockGetFlowLogs(knownFlowId);
    for (let i = 1; i < logs.length; i++) {
      expect(logs[i].t).toBeGreaterThanOrEqual(logs[i - 1].t);
    }
  });
});
