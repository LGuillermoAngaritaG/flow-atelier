import { USE_MOCK } from "@/services/client";
import type { Conduit } from "@/types/conduit";
import type { PriorFlow } from "@/types/flow";
import type { ScheduledJob } from "@/types/schedule";

import {
  conduits as mockConduits,
  getConduit as mockGetConduit,
} from "@/services/mock/conduits";
import { priorFlows as mockPriorFlows, mockGetFlowLogs } from "@/services/mock/flows";
import { mockScheduledJobs } from "@/services/mock/schedules";

import {
  getConduits as apiGetConduits,
  getConduitByName as apiGetConduitByName,
} from "@/services/api/conduits";
import { getFlows as apiGetFlows, getFlowLogs as apiGetFlowLogs } from "@/services/api/flows";
import { getSchedules as apiGetSchedules } from "@/services/api/schedules";

// ── Conduit list ──────────────────────────────────────────────────────────

let _conduitCache: Conduit[] | null = null;

export async function fetchConduits(): Promise<Conduit[]> {
  if (USE_MOCK) return mockConduits;
  if (_conduitCache) return _conduitCache;
  _conduitCache = await apiGetConduits();
  return _conduitCache;
}

export function clearConduitCache() {
  _conduitCache = null;
}

export function getConduitCached(name: string): Conduit | undefined {
  if (USE_MOCK) return mockGetConduit(name);
  return _conduitCache?.find((c) => c.name === name);
}

export async function fetchConduit(name: string): Promise<Conduit | undefined> {
  if (USE_MOCK) return mockGetConduit(name);
  if (_conduitCache) return _conduitCache.find((c) => c.name === name);
  // Let real errors propagate; swallowing them to `undefined` made a network
  // or permission failure indistinguishable from "this conduit doesn't exist."
  return apiGetConduitByName(name);
}

// ── Flows ─────────────────────────────────────────────────────────────────

export async function fetchFlows(): Promise<PriorFlow[]> {
  if (USE_MOCK) return mockPriorFlows;
  return apiGetFlows();
}

export async function fetchFlowLogs(flowId: string) {
  if (USE_MOCK) return { logs: mockGetFlowLogs(flowId), tasks: [], runPath: undefined, children: [] };
  return apiGetFlowLogs(flowId);
}

// ── Schedules ─────────────────────────────────────────────────────────────

export async function fetchSchedules(): Promise<ScheduledJob[]> {
  if (USE_MOCK) return mockScheduledJobs;
  return apiGetSchedules();
}
