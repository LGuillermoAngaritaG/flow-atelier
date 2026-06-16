import { describe, it, expect } from "vitest";
import { cn } from "@/lib/cn";

describe("cn", () => {
  it("merges class strings", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("filters falsy values", () => {
    expect(cn("foo", false && "bar", "baz")).toBe("foo baz");
  });

  it("deduplicates tailwind utility classes (last wins)", () => {
    expect(cn("px-4", "px-6")).toBe("px-6");
  });

  it("resolves conflicting tailwind classes", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("resolves partial conflicts and keeps non-conflicting classes", () => {
    expect(cn("p-2", "p-4", "m-2")).toBe("p-4 m-2");
  });

  it("returns empty string for all-falsy inputs", () => {
    expect(cn(undefined, null, "")).toBe("");
  });

  it("accepts array input", () => {
    expect(cn(["foo", "bar"])).toBe("foo bar");
  });

  it("accepts object input (truthy keys included)", () => {
    expect(cn({ foo: true, bar: false })).toBe("foo");
  });
});
