import type { ToolType } from "@/types/task";

export interface ToolMeta {
  name: ToolType;
  desc: string;
  color: string;
}

export const TOOL_META: ToolMeta[] = [
  { name: "tool:bash", desc: "Shell command via subprocess", color: "oklch(0.80 0.12 200)" },
  { name: "tool:conduit", desc: "Run another conduit", color: "oklch(0.80 0.12 145)" },
  { name: "harness:claude-code", desc: "Claude Code harness", color: "oklch(0.78 0.12 300)" },
  { name: "harness:codex", desc: "Codex harness", color: "oklch(0.78 0.12 330)" },
  { name: "harness:copilot", desc: "Copilot harness", color: "oklch(0.78 0.12 240)" },
  { name: "harness:cursor", desc: "Cursor harness", color: "oklch(0.78 0.12 270)" },
];

export const TOOL_COLORS: Partial<Record<ToolType, string>> = Object.fromEntries(
  TOOL_META.map((t) => [t.name, t.color]),
);
