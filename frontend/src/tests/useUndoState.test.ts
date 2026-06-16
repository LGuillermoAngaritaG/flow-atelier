// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useUndoState } from "@/hooks/useUndoState";
import { vi } from "vitest";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useUndoState", () => {
  it("returns initial value", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    expect(result.current[0]).toBe("hello");
  });

  it("supports lazy initializer", () => {
    const { result } = renderHook(() => useUndoState(() => "lazy"));
    expect(result.current[0]).toBe("lazy");
  });

  it("sets state with direct value", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    act(() => {
      result.current[1]("world");
    });
    expect(result.current[0]).toBe("world");
  });

  it("sets state with functional updater", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    act(() => {
      result.current[1]((prev) => prev + "!");
    });
    expect(result.current[0]).toBe("hello!");
  });

  it("undoes after debounce flushes", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    act(() => {
      result.current[1]("world");
    });
    act(() => {
      vi.advanceTimersByTime(400);
    });
    act(() => {
      result.current[2](); // undo
    });
    expect(result.current[0]).toBe("hello");
  });

  it("clears pending but cannot undo before debounce (history empty)", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    act(() => {
      result.current[1]("world");
    });
    // Undo immediately — pending is cleared, but history is empty so it's a no-op.
    // The state change was already committed by setStateRaw.
    act(() => {
      result.current[2](); // undo
    });
    expect(result.current[0]).toBe("world");
    // The pending entry was discarded, so flushing won't add to history either.
    act(() => {
      vi.advanceTimersByTime(400);
    });
    // Undo is still a no-op — no history was ever built.
    act(() => {
      result.current[2]();
    });
    expect(result.current[0]).toBe("world");
  });

  it("is a no-op when undo is called with empty history", () => {
    const { result } = renderHook(() => useUndoState("hello"));
    act(() => {
      result.current[2](); // undo with nothing to undo
    });
    expect(result.current[0]).toBe("hello");
  });

  it("coalesces rapid sets into one history entry", () => {
    const { result } = renderHook(() => useUndoState("initial"));
    act(() => {
      result.current[1]("a");
      result.current[1]("b");
      result.current[1]("c");
    });
    act(() => {
      vi.advanceTimersByTime(400);
    });
    // Only one undo should bring us back to "initial"
    act(() => {
      result.current[2](); // undo
    });
    expect(result.current[0]).toBe("initial");
  });

  it("enforces MAX_HISTORY=50 cap", () => {
    const { result } = renderHook(() => useUndoState(0));
    // Make 51 distinct state changes with debounce flushes
    for (let i = 1; i <= 51; i++) {
      act(() => {
        result.current[1](i);
      });
      act(() => {
        vi.advanceTimersByTime(400);
      });
    }
    // State should be 51
    expect(result.current[0]).toBe(51);
    // 50 undos should work (history capped at 50, first entry was dropped)
    for (let i = 0; i < 50; i++) {
      act(() => {
        result.current[2]();
      });
    }
    // After 50 undos we're at state 1 (the first entry was evicted)
    expect(result.current[0]).toBe(1);
    // 51st undo is a no-op — history exhausted
    act(() => {
      result.current[2]();
    });
    expect(result.current[0]).toBe(1);
  });
});
