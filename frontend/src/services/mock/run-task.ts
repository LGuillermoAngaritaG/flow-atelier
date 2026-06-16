import type { RunTaskResponse } from "@/types/api";
import type { LogEntry } from "@/types/task";

const NOW = Date.now();
const S = 1_000;

export const mockTaskRunLogs: LogEntry[] = [
  { t: NOW + 0 * S, text: "▸ task queued", level: "info" },
  { t: NOW + 1 * S, text: "▸ starting agent", level: "info" },
  { t: NOW + 2 * S, text: "  reading run path …", level: "info" },
  { t: NOW + 3 * S, text: "  loading task context …", level: "info" },
  { t: NOW + 5 * S, text: "  executing task …", level: "info" },
  { t: NOW + 8 * S, text: "  processing output …", level: "info" },
  { t: NOW + 10 * S, text: "✓ task completed", level: "ok" },
];

export function mockRunTask(): RunTaskResponse {
  return {
    flowId: `FLOW-${Date.now()}`,
    logs: mockTaskRunLogs,
  };
}
