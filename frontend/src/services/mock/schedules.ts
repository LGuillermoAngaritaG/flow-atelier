import type { ScheduledJob } from "@/types/schedule";
import type { CreateScheduleRequest } from "@/types/api";

const REF = Date.parse("2026-04-20T12:00:00Z");
const HR = 3_600_000;
const DAY = 24 * HR;

export const mockScheduledJobs: ScheduledJob[] = [
  {
    id: "SCH-001",
    conduitName: "nightly_backup",
    inputs: { bucket: "atelier-cold" },
    schedule: {
      mode: "recurring",
      days: [1, 2, 3, 4, 5],
      times: ["02:00"],
    },
    createdAt: REF - 7 * DAY,
    status: "active",
    runsCompleted: 7,
    nextRunAt: REF + 14 * HR,
  },
  {
    id: "SCH-002",
    conduitName: "triage_inbox",
    inputs: { project: "NEO" },
    schedule: {
      mode: "recurring",
      days: [1, 2, 3, 4, 5, 6, 7],
      times: ["06:00", "12:00", "18:00"],
      maxRuns: 10,
    },
    createdAt: REF - 2 * DAY,
    status: "active",
    runsCompleted: 8,
    nextRunAt: REF + 2 * HR,
  },
  {
    id: "SCH-003",
    conduitName: "release_notes",
    inputs: { repo: "flow/atelier", from: "v0.4.2", to: "HEAD" },
    schedule: {
      mode: "once",
      runAt: new Date(REF + 4 * HR).toISOString(),
    },
    createdAt: REF - 1 * HR,
    status: "active",
    runsCompleted: 0,
    nextRunAt: REF + 4 * HR,
  },
  {
    id: "SCH-004",
    conduitName: "bench_compile",
    inputs: { branch: "feat/simd", iters: "5" },
    schedule: {
      mode: "recurring",
      days: [1, 3, 5],
      times: ["09:00", "15:00"],
      maxRuns: 5,
    },
    createdAt: REF - 4 * DAY,
    status: "completed",
    runsCompleted: 5,
    nextRunAt: undefined,
  },
];

// ── Mock API handlers ─────────────────────────────────────────────────────

let jobs = [...mockScheduledJobs];

export function mockGetSchedules(): ScheduledJob[] {
  return jobs;
}

function computeNextRun(days: number[], times: string[]): number {
  const now = Date.now();
  const sorted = [...times].sort();
  for (let offset = 0; offset < 8; offset++) {
    const d = new Date(now);
    d.setDate(d.getDate() + offset);
    const isoDay = d.getDay() === 0 ? 7 : d.getDay();
    if (!days.includes(isoDay)) continue;
    for (const t of sorted) {
      const [h, m] = t.split(":").map(Number);
      d.setHours(h, m, 0, 0);
      if (d.getTime() > now) return d.getTime();
    }
  }
  return now + 86_400_000;
}

export function mockCreateSchedule(req: CreateScheduleRequest): ScheduledJob {
  const { schedule } = req;
  let nextRunAt: number | undefined;
  if (schedule.mode === "once" && schedule.runAt) {
    nextRunAt = new Date(schedule.runAt).getTime();
  } else if (schedule.mode === "recurring" && schedule.days?.length && schedule.times?.length) {
    nextRunAt = computeNextRun(schedule.days, schedule.times);
  }
  const job: ScheduledJob = {
    id: `SCH-${String(Date.now()).slice(-4)}`,
    conduitName: req.conduitName,
    inputs: req.inputs,
    runPath: req.runPath,
    schedule: req.schedule,
    createdAt: Date.now(),
    status: "active",
    runsCompleted: 0,
    nextRunAt,
  };
  jobs = [job, ...jobs];
  return job;
}

export function mockDeleteSchedule(id: string): ScheduledJob {
  const job = jobs.find((j) => j.id === id);
  if (!job) throw new Error(`Schedule ${id} not found`);
  job.status = "deleted";
  return job;
}
