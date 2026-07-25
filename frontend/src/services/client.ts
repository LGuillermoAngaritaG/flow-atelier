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
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    // A transport failure (server down, DNS, CORS) surfaces as a bare
    // "Failed to fetch", which tells the user nothing actionable.
    throw new Error(`Can't reach the flow-atelier API at ${BASE_URL}`);
  }
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API error ${res.status}: ${errorText}`);
  }
  // A successful call may have no body (e.g. a 204 DELETE). Parsing an empty
  // string as JSON throws, so a successful delete would surface as an error.
  const text = await res.text();
  if (!text) return undefined as TResponse;
  try {
    return toCamelCase<TResponse>(JSON.parse(text));
  } catch {
    // A 200 that isn't JSON means we hit something other than the API — most
    // often an SPA index.html from a dev server with no backend behind it.
    // The raw SyntaxError ("Unexpected token '<', \"<!doctype \"...") used to
    // reach the user verbatim as the entire error message.
    throw new Error(
      `Expected JSON from ${url} but got ${res.headers.get("content-type") ?? "an unknown type"}. ` +
        `Is the flow-atelier API running at ${BASE_URL}?`,
    );
  }
}

export { USE_MOCK, BASE_URL };
