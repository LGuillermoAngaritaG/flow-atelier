import type { Task } from "@/types/task";

const NOW = Date.now();
const MIN = 60_000;
const HR = 60 * MIN;
const P = "default";

export const seedTasks: Task[] = [
  // ─── todo ────────────────────────────────────────────────────────────
  {
    name: "release_notes",
    projectId: P,
    inputs: { repo: "flow/atelier", from: "v0.4.2", to: "HEAD" },
    createdAt: NOW - 15 * MIN,
    column: "todo",
  },
  {
    name: "nightly_backup",
    projectId: P,
    inputs: { bucket: "atelier-cold" },
    createdAt: NOW - 42 * MIN,
    column: "todo",
  },

  // ─── done ────────────────────────────────────────────────────────────
  {
    name: "deploy_pipeline",
    projectId: P,
    inputs: { service: "web-app", ref: "staging" },
    createdAt: NOW - 2 * HR,
    column: "done",
  },
  {
    name: "bench_compile",
    projectId: P,
    inputs: { branch: "feat/simd", iters: "5" },
    createdAt: NOW - 6 * HR,
    column: "done",
  },
  {
    name: "triage_inbox",
    projectId: P,
    inputs: { project: "NEO" },
    createdAt: NOW - 12 * HR,
    column: "done",
  },
];
