import { fetchJson, USE_MOCK, BASE_URL } from "@/services/client";
import {
  mockGetSchedules,
  mockCreateSchedule,
  mockDeleteSchedule,
} from "@/services/mock/schedules";
import type { ScheduledJob } from "@/types/schedule";
import type { CreateScheduleRequest } from "@/types/api";

export async function getSchedules(): Promise<ScheduledJob[]> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] GET /schedules`);
  if (USE_MOCK) {
    return mockGetSchedules();
  }

  return fetchJson<ScheduledJob[]>(`${BASE_URL}/schedules`, undefined, {
    method: "GET",
  });
}

export async function createSchedule(
  req: CreateScheduleRequest,
): Promise<ScheduledJob> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] POST /schedules`, req);
  if (USE_MOCK) {
    return mockCreateSchedule(req);
  }

  return fetchJson<ScheduledJob>(`${BASE_URL}/schedules`, req);
}

export async function deleteSchedule(id: string): Promise<ScheduledJob> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] DELETE /schedules/${id}`);
  if (USE_MOCK) {
    return mockDeleteSchedule(id);
  }

  return fetchJson<ScheduledJob>(`${BASE_URL}/schedules/${id}`, undefined, {
    method: "DELETE",
  });
}
