import type { ScheduleConfig, ScheduledJob } from "./schedule";
import type { ToolType } from "./conduit";
import type { LogEntry } from "./task";

export interface CreateScheduleRequest {
  conduitName: string;
  inputs: Record<string, string>;
  runPath?: string;
  schedule: ScheduleConfig;
}

export type CreateScheduleResponse = ScheduledJob;

export interface RunTaskRequest {
  name: string;
  description?: string;
  tool?: ToolType;
  runPath?: string;
  task?: string;
}

export interface RunTaskResponse {
  flowId: string;
  logs: LogEntry[];
}
