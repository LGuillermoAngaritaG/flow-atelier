export type ScheduleMode = "once" | "recurring";

export interface ScheduleConfig {
  mode: ScheduleMode;
  name?: string;
  runAt?: string; // ISO datetime string — used for "once" mode
  days?: number[]; // 1=Mon through 7=Sun (ISO 8601) — used for "recurring" mode
  times?: string[]; // "HH:mm" 24-hour format — used for "recurring" mode
  maxRuns?: number; // undefined = unlimited
}

export interface ScheduledJob {
  id: string;
  conduitName: string;
  inputs: Record<string, string>;
  runPath?: string;
  schedule: ScheduleConfig;
  createdAt: number;
  status: "active" | "paused" | "completed" | "deleted";
  runsCompleted: number;
  nextRunAt?: number; // ms timestamp
}
