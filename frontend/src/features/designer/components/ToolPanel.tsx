import { useState } from "react";
import type { ConduitTask, InputSpec, ToolType } from "@/types/conduit";
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
    color: "oklch(0.75 0.15 60)",
  },
  {
    name: "tool:conduit",
    desc: "Recurse into another conduit",
    color: "oklch(0.80 0.12 145)",
  },
  {
    name: "harness:claude-code",
    desc: "Inline Claude Code harness",
    color: "#c15f3c",
  },
  {
    name: "harness:codex",
    desc: "Codex harness",
    color: "#E8EEFF",
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

import type { Conduit } from "@/types/conduit";

interface Props {
  conduit: Conduit;
  conduitInputs: Record<string, string | InputSpec>;
  onAddTask: (task: ConduitTask) => void;
  onAddInput: (name: string, hint: string) => void;
  onRemoveInput: (name: string) => void;
}

export function ToolPanel({ conduit, conduitInputs, onAddTask, onAddInput, onRemoveInput }: Props) {
  const [isCreatingInput, setIsCreatingInput] = useState(false);
  const [newInputName, setNewInputName] = useState("");
  const [newInputHint, setNewInputHint] = useState("");

  const handleAdd = (tool: ToolRow) => {
    const task: ConduitTask = {
      name: "",
      tool: tool.name,
      description: "",
      task: "",
      dependsOn: [],
    };
    onAddTask(task);
  };

  const handleCreateInput = () => {
    const name = newInputName.trim();
    if (!name) return;
    if (name in conduitInputs) return;
    onAddInput(name, newInputHint.trim());
    setNewInputName("");
    setNewInputHint("");
    setIsCreatingInput(false);
  };

  return (
    <div
      data-testid="designer-tool-panel"
      className="overflow-auto bg-background"
    >
      <div className="border-b border-border/60 px-5 py-5">
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
          conduit
        </div>
        <h2 className="mt-1 font-display text-[18px] leading-tight tracking-[-0.01em] text-foreground">
          {conduit.name || "untitled"}
        </h2>
        {conduit.description && (
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            {conduit.description}
          </p>
        )}
      </div>

      <div className="px-4 py-4">
        <div className="flex flex-col gap-2">
          {TOOLS.map((t) => (
            <button
              key={t.name}
              type="button"
              onClick={() => handleAdd(t)}
              className="group w-full rounded-md border border-border/60 bg-background px-3 py-2.5 text-left transition-colors hover:border-border hover:bg-muted/50"
            >
              <div
                className="font-mono text-[12px] leading-tight font-bold"
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

      <div className="border-t border-border/60 px-4 py-5">
        <span className="mb-3 block font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
          inputs
        </span>
        {Object.keys(conduitInputs).length > 0 && (
          <div className="mb-3 flex flex-col gap-1">
            {Object.entries(conduitInputs).map(([name, hint]) => (
              <div
                key={name}
                className="flex items-start justify-between gap-1 rounded-md border border-border/50 px-2.5 py-2"
              >
                <div className="min-w-0">
                  <div className="font-mono text-[11px] leading-tight text-foreground">
                    {name}
                  </div>
                  {hintStr(hint) && (
                    <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                      {hintStr(hint)}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  aria-label={`remove input ${name}`}
                  onClick={() => onRemoveInput(name)}
                  className="shrink-0 text-muted-foreground/60 hover:text-destructive"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        {isCreatingInput ? (
          <div className="space-y-2 border border-border/60 p-2">
            <label htmlFor="toolpanel-input-name" className="sr-only">input name</label>
            <input
              id="toolpanel-input-name"
              placeholder="name"
              value={newInputName}
              onChange={(e) => setNewInputName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateInput();
              }}
              className="w-full border-0 border-b border-border bg-transparent pb-1 font-mono text-[11px] text-foreground outline-none focus:border-primary"
            />
            <label htmlFor="toolpanel-input-desc" className="sr-only">input description</label>
            <input
              id="toolpanel-input-desc"
              placeholder="description"
              value={newInputHint}
              onChange={(e) => setNewInputHint(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateInput();
              }}
              className="w-full border-0 border-b border-border bg-transparent pb-1 font-mono text-[11px] text-foreground outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={handleCreateInput}
              className="w-full border border-primary py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-primary hover:bg-primary hover:text-primary-foreground"
            >
              create
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setIsCreatingInput(true)}
            className="flex items-center gap-1 font-mono text-[11px] text-primary hover:underline"
          >
            + add input
          </button>
        )}
      </div>
    </div>
  );
}
