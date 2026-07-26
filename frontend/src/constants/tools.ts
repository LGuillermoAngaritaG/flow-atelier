import type { ToolType } from "@/types/conduit";

/**
 * The one description of every tool. There used to be four copies of this
 * (designer TaskNode, designer ToolPanel, designer Inspector, kanban toolMeta)
 * and they had drifted: `harness:claude-code` rendered purple in a canvas node
 * and terracotta in the palette beside it, `harness:codex` was near-white in
 * two files and pink in the other two, and `tool:hitl` was missing entirely
 * from one of them.
 *
 * Colours are token references, not literals, so each one resolves to a
 * lightness that clears 4.5:1 against whichever theme is active — the old
 * literals were tuned for the dark surface and measured 1.1-2.2:1 on light.
 */
export interface ToolMeta {
  name: ToolType;
  desc: string;
  color: string;
}

export const TOOL_META: ToolMeta[] = [
  {
    name: "tool:bash",
    desc: "Shell command via subprocess",
    color: "var(--color-tool-bash)",
  },
  {
    name: "tool:hitl",
    desc: "Prompt a human for named inputs",
    color: "var(--color-tool-hitl)",
  },
  {
    name: "tool:conduit",
    desc: "Recurse into another conduit",
    color: "var(--color-tool-conduit)",
  },
  {
    name: "harness:claude-code",
    desc: "Inline Claude Code harness",
    color: "var(--color-tool-claude-code)",
  },
  {
    name: "harness:codex",
    desc: "Codex harness",
    color: "var(--color-tool-codex)",
  },
  {
    name: "harness:opencode",
    desc: "opencode harness",
    color: "var(--color-tool-opencode)",
  },
  {
    name: "harness:copilot",
    desc: "Copilot harness",
    color: "var(--color-tool-copilot)",
  },
  {
    name: "harness:cursor",
    desc: "Cursor harness",
    color: "var(--color-tool-cursor)",
  },
];

export const TOOL_COLORS: Record<ToolType, string> = Object.fromEntries(
  TOOL_META.map((t) => [t.name, t.color]),
) as Record<ToolType, string>;
