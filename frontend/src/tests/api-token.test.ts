import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { getApiToken, setApiToken } from "@/config/env";
import { fetchJson } from "@/services/client";

/**
 * The token is read at runtime, not compiled in: the SPA that ships in the
 * wheel is built once for everyone, so a build-time constant is empty in every
 * installed copy and the bundled UI could never authenticate against a server
 * started with ATELIER_API_TOKEN.
 */
describe("runtime API token", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("round-trips through sessionStorage", () => {
    expect(getApiToken()).toBe("");
    setApiToken("s3cret");
    expect(getApiToken()).toBe("s3cret");
  });

  it("sends no Authorization header when no token is set", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await fetchJson("http://x/conduits", undefined, { method: "GET" });
    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers.Authorization).toBeUndefined();
  });

  it("sends a stored token as a bearer header", async () => {
    setApiToken("s3cret");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await fetchJson("http://x/conduits", undefined, { method: "GET" });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer s3cret");
  });

  it("prompts on a 401, stores the token, and retries once", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("nope", { status: 401 }))
      .mockResolvedValueOnce(
        new Response('{"ok":true}', {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("from-user"));

    const body = await fetchJson<{ ok: boolean }>("http://x/conduits", undefined, {
      method: "GET",
    });

    expect(body.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer from-user");
    // Kept for the tab, so the next call and the WS handshake don't re-ask.
    expect(getApiToken()).toBe("from-user");
  });

  it("does not re-prompt in a loop when the entered token is also rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 401 }));
    const promptMock = vi.fn().mockReturnValue("wrong");
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("prompt", promptMock);

    await expect(
      fetchJson("http://x/conduits", undefined, { method: "GET" }),
    ).rejects.toThrow("API error 401");
    expect(promptMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("lets the 401 stand when the user dismisses the prompt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("prompt", vi.fn().mockReturnValue(null));

    await expect(
      fetchJson("http://x/conduits", undefined, { method: "GET" }),
    ).rejects.toThrow("API error 401");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
