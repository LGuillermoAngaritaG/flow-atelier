import { describe, it, expect } from "vitest";
import { createPrng, intBetween } from "@/runner/prng";

describe("createPrng", () => {
  it("produces a deterministic sequence for the same seed", () => {
    const a = createPrng(42);
    const b = createPrng(42);
    const seqA = Array.from({ length: 10 }, () => a());
    const seqB = Array.from({ length: 10 }, () => b());
    expect(seqA).toEqual(seqB);
  });

  it("produces different values for different seeds", () => {
    const a = createPrng(1);
    const b = createPrng(2);
    expect(a()).not.toBe(b());
  });

  it("returns values in [0, 1)", () => {
    const rng = createPrng(0xa71e);
    for (let i = 0; i < 1000; i++) {
      const v = rng();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe("intBetween", () => {
  it("produces integers within [lo, hi]", () => {
    const rng = createPrng(123);
    for (let i = 0; i < 100; i++) {
      const v = intBetween(rng, 1, 6);
      expect(Number.isInteger(v)).toBe(true);
      expect(v).toBeGreaterThanOrEqual(1);
      expect(v).toBeLessThanOrEqual(6);
    }
  });

  it("returns lo when lo === hi", () => {
    const rng = createPrng(99);
    for (let i = 0; i < 20; i++) {
      expect(intBetween(rng, 10, 10)).toBe(10);
    }
  });

  it("covers the full range over many samples", () => {
    const rng = createPrng(456);
    const values = new Set<number>();
    for (let i = 0; i < 200; i++) {
      values.add(intBetween(rng, 1, 6));
    }
    // With 200 rolls of a d6 we should see all faces
    expect(values.size).toBe(6);
  });
});
