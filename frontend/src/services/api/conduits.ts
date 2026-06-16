import { fetchJson, USE_MOCK, BASE_URL } from "@/services/client";
import {
  mockGetConduits,
  mockGetConduit,
  mockOpenPath,
  mockCreateConduit,
  mockUpdateConduit,
} from "@/services/mock/conduits";
import type { Conduit, CreateConduitRequest } from "@/types/conduit";

export async function getConduits(): Promise<Conduit[]> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] GET /conduits`);
  if (USE_MOCK) {
    return mockGetConduits();
  }

  return fetchJson<Conduit[]>(`${BASE_URL}/conduits`, undefined, {
    method: "GET",
  });
}

export async function getConduitByName(name: string): Promise<Conduit> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] GET /conduits/${name}`);
  if (USE_MOCK) {
    const c = mockGetConduit(name);
    if (!c) throw new Error(`Conduit ${name} not found`);
    return c;
  }

  return fetchJson<Conduit>(`${BASE_URL}/conduits/${name}`, undefined, {
    method: "GET",
  });
}

export async function openPath(
  conduitName: string,
  runPath: string,
): Promise<{ opened: boolean }> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] POST /conduits/open-path`);
  if (USE_MOCK) {
    return mockOpenPath(conduitName);
  }

  return fetchJson<{ opened: boolean }>(`${BASE_URL}/conduits/open-path`, {
    conduitName,
    runPath,
  });
}

export async function createConduit(
  req: CreateConduitRequest,
): Promise<Conduit> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] POST /conduits`, req);
  if (USE_MOCK) {
    return mockCreateConduit(req);
  }

  return fetchJson<Conduit>(`${BASE_URL}/conduits`, req, {
    method: "POST",
  });
}

export async function updateConduit(
  req: CreateConduitRequest,
): Promise<Conduit> {
  if (import.meta.env.DEV) console.log(`[${USE_MOCK ? "mock" : "api"}] PATCH /conduits/${req.name}`, req);
  if (USE_MOCK) {
    return mockUpdateConduit(req);
  }

  return fetchJson<Conduit>(`${BASE_URL}/conduits/${req.name}`, req, {
    method: "PATCH",
  });
}
