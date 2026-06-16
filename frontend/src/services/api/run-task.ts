import { fetchJson, USE_MOCK, BASE_URL } from "@/services/client";
import { mockRunTask } from "@/services/mock/run-task";
import type { RunTaskRequest, RunTaskResponse } from "@/types/api";
import type { LogEntry } from "@/types/task";

interface BackendLogEntry {
  task: string;
  tool: string;
  iteration: number;
  of: number;
  command: string;
  stdout: string;
  stderr: string;
  exitCode: number;
}

interface BackendRunTaskResponse {
  flowId: string;
  logs: BackendLogEntry[];
}

export function toFrontendLogEntry(entry: BackendLogEntry): LogEntry {
  const parts = [entry.command, entry.stdout, entry.stderr].filter(Boolean);
  return {
    t: Date.now(),
    text: parts.join("\n"),
    level: entry.exitCode === 0 ? "info" : ("err" as const),
  };
}

export async function runTask(req: RunTaskRequest): Promise<RunTaskResponse> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] POST /tasks/run`, req);
  if (USE_MOCK) {
    return mockRunTask();
  }

  const raw = await fetchJson<BackendRunTaskResponse>(`${BASE_URL}/tasks/run`, req);
  return {
    flowId: raw.flowId,
    logs: raw.logs.map(toFrontendLogEntry),
  };
}
