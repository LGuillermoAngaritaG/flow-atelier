import type { ConduitTask, ToolType } from "@/types/conduit";
import { hintStr } from "@/types/conduit";

interface ToolRow {
  name: ToolType;
  desc: string;
  color: string;
}

const TOOLS: ToolRow[] = [
  {
    name: "tool:bash",
    desc: "Shell command via subprocess",
    color: "oklch(0.80 0.12 200)",
  },
  {
    name: "tool:hitl",
    desc: "Prompt a human for named inputs",
    color: "var(--color-primary)",
  },
  {
    name: "tool:conduit",
    desc: "Recurse into another conduit",
    color: "oklch(0.80 0.12 145)",
  },
  {
    name: "harness:claude-code",
    desc: "Inline Claude Code harness",
    color: "oklch(0.78 0.12 300)",
  },
  {
    name: "harness:codex",
    desc: "Codex harness",
    color: "oklch(0.78 0.12 330)",
  },
  {
    name: "harness:copilot",
    desc: "Copilot harness",
    color: "oklch(0.78 0.12 240)",
  },
  {
    name: "harness:cursor",
    desc: "Cursor harness",
    color: "oklch(0.78 0.12 270)",
  },
];

interface PaletteProps {
  conduitName: string;
  conduitInputs: Record<string, string>;
  onAddTask: (task: ConduitTask) => void;
}

let taskCounter = 0;

export function Palette({ conduitName, conduitInputs, onAddTask }: PaletteProps) {
  const handleAdd = (tool: ToolRow) => {
    taskCounter += 1;
    const task: ConduitTask = {
      name: `${tool.name.replace(/[:]/g, "_")}_${taskCounter}`,
      tool: tool.name,
      description: tool.desc,
      task: "",
      dependsOn: [],
      position: { x: 80 + Math.random() * 400, y: 100 + Math.random() * 200 },
    };
    onAddTask(task);
  };

  return (
    <aside
      data-testid="designer-palette"
      className="w-[232px] shrink-0 overflow-auto border-r border-border bg-background py-7"
    >
      <div className="border-b border-border/60 px-5 pb-6">
        <h2
          className="font-display text-[26px] leading-none tracking-[-0.01em]"
          data-testid="designer-conduit-name"
        >
          {conduitName.replace(/_/g, "_\n")}
        </h2>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          designer · editing
        </div>
      </div>

      <div className="px-4 py-5">
        <span className="mb-3 block font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
          Add nodes
        </span>
        <div className="flex flex-col gap-2">
          {TOOLS.map((t) => (
            <button
              key={t.name}
              type="button"
              onClick={() => handleAdd(t)}
              className="group w-full rounded-md border border-border/60 bg-background px-3 py-2.5 text-left transition-colors hover:border-border hover:bg-muted/50"
            >
              <div
                className="font-mono text-[12px] leading-tight"
                style={{ color: t.color }}
              >
                {t.name}
              </div>
              <div className="mt-1 text-[11px] leading-snug text-muted-foreground">
                {t.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      {Object.keys(conduitInputs).length > 0 && (
        <div className="border-t border-border/60 px-4 py-5">
          <span className="mb-3 block font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
            conduit inputs
          </span>
          <div className="flex flex-col gap-1.5">
            {Object.entries(conduitInputs).map(([name, hint]) => (
              <div
                key={name}
                className="font-mono text-[11px] text-foreground/80"
              >
                <span className="text-primary">{"{{"}</span>
                inputs.{name}
                <span className="text-primary">{"}}"}</span>
                {hintStr(hint) && (
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    {hintStr(hint)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
