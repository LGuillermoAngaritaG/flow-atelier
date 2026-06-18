// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, cleanup } from "@testing-library/react";

const fetchConduits = vi.fn();
vi.mock("@/services/conduits", () => ({
  fetchConduits: () => fetchConduits(),
  clearConduitCache: vi.fn(),
}));
vi.mock("@/services/client", () => ({ USE_MOCK: false }));

import { ConduitProvider } from "@/services/ConduitProvider";

beforeEach(() => {
  vi.useFakeTimers();
  fetchConduits.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ConduitProvider polling", () => {
  it("stops fetching once a non-empty list has loaded", async () => {
    fetchConduits.mockResolvedValue([{ name: "demo" }]);

    render(
      <ConduitProvider>
        <div />
      </ConduitProvider>,
    );

    // initial mount load
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchConduits).toHaveBeenCalledTimes(1);

    // advance well past several 5s poll intervals — no further fetches
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(fetchConduits).toHaveBeenCalledTimes(1);
  });

  it("stops fetching after a successful empty response", async () => {
    fetchConduits.mockResolvedValue([]);

    render(
      <ConduitProvider>
        <div />
      </ConduitProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchConduits).toHaveBeenCalledTimes(1);

    // an empty list is a valid loaded state — no forever-poll
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(fetchConduits).toHaveBeenCalledTimes(1);
  });

  it("retries on the timer while fetches keep failing", async () => {
    fetchConduits.mockRejectedValue(new Error("network down"));

    render(
      <ConduitProvider>
        <div />
      </ConduitProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchConduits).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchConduits).toHaveBeenCalledTimes(2);
  });
});
