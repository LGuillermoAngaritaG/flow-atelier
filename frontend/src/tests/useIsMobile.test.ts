// @vitest-environment jsdom
import { describe, it, expect, beforeAll } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIsMobile } from "@/hooks/useIsMobile";

function createMatchMedia(initialMatches: boolean) {
  let listener: ((e: Partial<MediaQueryListEvent>) => void) | null = null;
  return {
    install() {
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        value: (query: string) => ({
          matches: initialMatches,
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: (_event: string, handler: (e: Partial<MediaQueryListEvent>) => void) => {
            listener = handler;
          },
          removeEventListener: () => {
            listener = null;
          },
          dispatchEvent: () => false,
        }),
      });
    },
    setMatches(matches: boolean) {
      listener?.({ matches } as Partial<MediaQueryListEvent>);
    },
  };
}

beforeAll(() => {
  // Default: non-mobile
  createMatchMedia(false).install();
});

describe("useIsMobile", () => {
  it("returns false for non-mobile viewport", () => {
    createMatchMedia(false).install();
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it("returns true for mobile viewport", () => {
    createMatchMedia(true).install();
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("updates when viewport changes", () => {
    const mm = createMatchMedia(false);
    mm.install();
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    act(() => {
      mm.setMatches(true);
    });
    expect(result.current).toBe(true);
  });
});
