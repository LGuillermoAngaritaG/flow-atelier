import { API_TOKEN, BASE_URL, USE_MOCK } from "@/config/env";
import { toCamelCase, toSnakeCase } from "./transforms";

export async function fetchJson<TResponse>(
  url: string,
  body?: unknown,
  options?: {
    method?: string;
    headers?: Record<string, string>;
  },
): Promise<TResponse> {
  const { method = "POST", headers } = options ?? {};
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
      ...headers,
    },
  };
  if (method !== "GET" && body !== undefined) {
    init.body = JSON.stringify(toSnakeCase(body));
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API error ${res.status}: ${errorText}`);
  }
  const json = await res.json();
  return toCamelCase<TResponse>(json);
}

export { USE_MOCK, BASE_URL };
