import type { PriorFlow } from "@/types/flow";
import { mockGetFlowLogs } from "@/services/mock/logs";

// ── Mock API handlers ─────────────────────────────────────────────────────

export function mockGetFlows(): PriorFlow[] {
  return priorFlows;
}

export { mockGetFlowLogs };

// -------------------------------------------------------------------------
// 12 prior flows for the history tabular list.
// Dates are authored as offsets from a fixed reference so seed is stable.
// -------------------------------------------------------------------------

const REF = Date.parse("2026-04-15T18:00:00Z");
const MIN = 60_000;
const HR = 60 * MIN;

export const priorFlows: PriorFlow[] = [
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012048abcde",
    conduitName: "release_notes",
    startedAt: REF - 2 * HR,
    duration: 4 * MIN,
    status: "done",
    author: "john-doe",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012047abcde",
    conduitName: "deploy_pipeline",
    startedAt: REF - 3 * HR - 12 * MIN,
    duration: 6 * MIN + 20_000,
    status: "done",
    author: "john-doe",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012046abcde",
    conduitName: "deploy_pipeline",
    startedAt: REF - 4 * HR,
    duration: 2 * MIN + 10_000,
    status: "failed",
    author: "c.fischer",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012045abcde",
    conduitName: "triage_inbox",
    startedAt: REF - 5 * HR - 44 * MIN,
    duration: 80_000,
    status: "done",
    author: "r.kovac",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012044abcde",
    conduitName: "onboard_repo",
    startedAt: REF - 7 * HR,
    duration: 11 * MIN,
    status: "done",
    author: "m.price",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012043abcde",
    conduitName: "nightly_backup",
    startedAt: REF - 11 * HR,
    duration: 8 * MIN,
    status: "done",
    author: "cron",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012042abcde",
    conduitName: "bench_compile",
    startedAt: REF - 13 * HR,
    duration: 17 * MIN,
    status: "done",
    author: "j.lin",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012041abcde",
    conduitName: "release_notes",
    startedAt: REF - 26 * HR,
    duration: 3 * MIN + 40_000,
    status: "done",
    author: "john-doe",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012040abcde",
    conduitName: "deploy_pipeline",
    startedAt: REF - 28 * HR,
    duration: 6 * MIN,
    status: "done",
    author: "c.fischer",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012039abcde",
    conduitName: "triage_inbox",
    startedAt: REF - 32 * HR,
    duration: 70_000,
    status: "cancelled",
    author: "r.kovac",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012038abcde",
    conduitName: "nightly_backup",
    startedAt: REF - 35 * HR,
    duration: 7 * MIN + 30_000,
    status: "done",
    author: "cron",
  },
  {
    flowId: "a1b2c3d4-5678-4abc-9def-0012037abcde",
    conduitName: "onboard_repo",
    startedAt: REF - 48 * HR,
    duration: 14 * MIN,
    status: "done",
    author: "m.price",
  },
];
