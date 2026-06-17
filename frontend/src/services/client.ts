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
  // A successful call may have no body (e.g. a 204 DELETE). Parsing an empty
  // string as JSON throws, so a successful delete would surface as an error.
  const text = await res.text();
  if (!text) return undefined as TResponse;
  return toCamelCase<TResponse>(JSON.parse(text));
}

export { USE_MOCK, BASE_URL };
