import { describe, it, expect } from "vitest";
import { parseTs } from "@/services/api/flows";

describe("parseTs", () => {
  it("parses a valid ISO timestamp to epoch ms", () => {
    expect(parseTs("2026-01-02T03:04:05Z")).toBe(Date.parse("2026-01-02T03:04:05Z"));
  });

  it("returns null for empty / missing input (not Date.now())", () => {
    expect(parseTs("")).toBeNull();
    expect(parseTs(null)).toBeNull();
    expect(parseTs(undefined)).toBeNull();
  });

  it("returns null for garbage input instead of falling back to now", () => {
    expect(parseTs("not-a-date")).toBeNull();
  });
});
