import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { ToolType } from "@/types/conduit";
import { Repeat } from "lucide-react";
import { cn } from "@lib/cn";

export interface TaskNodeData extends Record<string, unknown> {
  idx: number;
  name: string;
  tool: ToolType;
  task: string;
  description: string;
  repeat?: number;
  conditional?: "match" | "not_match";
}

const TOOL_COLOR: Record<ToolType, string> = {
  "tool:bash": "oklch(0.80 0.12 200)",
  "tool:hitl": "oklch(0.75 0.15 60)",
  "tool:conduit": "oklch(0.80 0.12 145)",
  "harness:claude-code": "oklch(0.78 0.12 300)",
  "harness:codex": "oklch(0.78 0.12 330)",
  "harness:copilot": "oklch(0.78 0.12 240)",
  "harness:cursor": "oklch(0.78 0.12 270)",
};

export function TaskNode({ data, selected }: NodeProps) {
  const d = data as TaskNodeData;
  return (
    <div
      data-testid="task-node"
      data-node-name={d.name}
      className={cn(
        "relative w-[220px] min-h-[88px] border border-border bg-muted font-mono text-foreground isolate",
        selected && "border-primary shadow-[0_0_0_1px_var(--color-primary)]",
      )}
    >
      {d.repeat != null && d.repeat > 1 && (
        <div className="absolute -top-4 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-full border border-green-600/60 bg-green-500/10 px-2 py-0.5">
          <Repeat className="size-3 text-green-600" />
          <span className="font-mono text-[9px] text-green-600">×{d.repeat}</span>
        </div>
      )}
      <div className="px-3 py-2">
        <span
          className="font-mono text-[9px] uppercase tracking-[0.14em]"
          style={{ color: TOOL_COLOR[d.tool] }}
          data-testid="n-tool"
        >
          {d.tool}
        </span>
      </div>
      <div className="min-h-[20px] px-3 pb-1 pt-0.5 text-[13px]">
        {d.name || " "}
      </div>
      <div className="min-h-[16px] px-3 pb-3 font-sans text-[11px] leading-snug text-muted-foreground">
        {d.description || " "}
      </div>

      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !-translate-x-1/2 !rounded-full !border-2 !border-muted-foreground/40 !bg-background"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !translate-x-1/2 !rounded-full !border-2 !border-muted-foreground/40 !bg-background"
      />
    </div>
  );
}
