import { describe, it, expect } from "vitest";
import { TOOL_META, toolColor } from "@/constants/tools";
import type { ToolType } from "@/types/conduit";

const names = TOOL_META.map((t) => t.name);

describe("TOOL_META", () => {
  it("keeps the three built-in tools", () => {
    expect(names).toEqual(
      expect.arrayContaining(["tool:bash", "tool:hitl", "tool:conduit"]),
    );
  });

  it("still offers the harnesses that predate the ACP registry", () => {
    expect(names).toEqual(
      expect.arrayContaining([
        "harness:claude-code",
        "harness:codex",
        "harness:opencode",
        "harness:copilot",
        "harness:cursor",
      ]),
    );
  });

  it("offers the newer registry agents", () => {
    expect(names).toEqual(
      expect.arrayContaining([
        "harness:gemini",
        "harness:qwen-code",
        "harness:goose",
        "harness:amp-acp",
        "harness:cline",
        "harness:auggie",
      ]),
    );
  });

  it("has no duplicate entries", () => {
    expect(new Set(names).size).toBe(names.length);
  });

  it("names a distinct colour token per tool", () => {
    const colors = TOOL_META.map((t) => t.color);
    expect(new Set(colors).size).toBe(colors.length);
    // Token references, not literals: each has to resolve per theme.
    colors.forEach((c) => expect(c).toMatch(/^var\(--color-tool-[a-z0-9-]+\)$/));
  });
});

describe("toolColor", () => {
  it("returns the palette colour for a known tool", () => {
    expect(toolColor("harness:gemini")).toBe("var(--color-tool-gemini)");
  });

  it("falls back for an agent outside the default palette", () => {
    // The designer palette is not the set of legal tools — the backend
    // accepts any registered harness:<name>, and those must still render.
    expect(toolColor("harness:mistral-vibe" as ToolType)).toBe(
      "var(--color-tool-harness-other)",
    );
    expect(toolColor("harness:my-private-agent" as ToolType)).toBe(
      "var(--color-tool-harness-other)",
    );
  });
});
