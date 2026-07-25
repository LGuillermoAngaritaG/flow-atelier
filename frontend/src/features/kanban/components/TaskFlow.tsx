import { X } from "lucide-react";
import type { ConduitTask, ToolType } from "@/types/conduit";
import { slugifyTaskName } from "@/types/conduit";
import { TOOL_META } from "@/constants/tools";
import { FieldRow } from "./FieldRow";
import { ProjectSelector } from "./ProjectSelector";

type NodeForm = { name: string; description: string; task: string; runPath: string };

interface Props {
  step: "task-nodes" | "node-detail";
  nodes: ConduitTask[];
  setNodes: React.Dispatch<React.SetStateAction<ConduitTask[]>>;
  nodeForm: NodeForm;
  setNodeForm: React.Dispatch<React.SetStateAction<NodeForm>>;
  runPath: string;
  setRunPath: (v: string) => void;
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
  projects: Array<{ id: string; name: string }>;
  openNodeForm: (tool: ToolType) => void;
  editNode: (idx: number) => void;
  fieldErrors: Record<string, string>;
}

export function TaskFlow({
  step,
  nodes,
  setNodes,
  nodeForm,
  setNodeForm,
  runPath,
  setRunPath,
  selectedProjectId,
  setSelectedProjectId,
  projects,
  openNodeForm,
  editNode,
  fieldErrors,
}: Props) {
  if (step === "task-nodes") {
    return (
      <div className="space-y-3">
        <div className="font-mono text-mini uppercase tracking-[0.12em] text-muted-foreground">
          click to add nodes
        </div>
        <div className="max-h-60 overflow-auto border border-border">
          {TOOL_META.map((t) => (
            <button
              key={t.name}
              type="button"
              onClick={() => openNodeForm(t.name)}
              className="grid w-full grid-cols-[28px_1fr] items-start gap-4 border-b border-border/50 px-4 py-3 text-left font-mono text-body last:border-b-0 hover:bg-muted/40"
            >
              <span
                className="mt-0.5 inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: t.color }}
              />
              <div className="min-w-0">
                <div className="text-data text-foreground">{t.name}</div>
                <div className="text-label text-muted-foreground">{t.desc}</div>
              </div>
            </button>
          ))}
        </div>
        {nodes.length > 0 && (
          <div className="space-y-1 border-t border-border/40 pt-2">
            <div className="font-mono text-micro uppercase tracking-[0.12em] text-muted-foreground">
              pipeline ({nodes.length})
            </div>
            {nodes.map((n, i) => {
              const meta = TOOL_META.find((t) => t.name === n.tool);
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => editNode(i)}
                  className="flex w-full items-center justify-between rounded border border-border/40 px-2 py-1.5 text-left transition-colors hover:border-border"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: meta?.color ?? "var(--color-muted)" }}
                    />
                    <span className="font-mono text-mini text-muted-foreground">{i + 1}. </span>
                    <span className="font-mono text-label text-foreground">{n.name}</span>
                    <span className="font-mono text-micro text-muted-foreground">{n.tool}</span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setNodes((prev) => prev.filter((_, j) => j !== i));
                    }}
                    aria-label="Remove step"
                    className="flex size-6 shrink-0 items-center justify-center text-muted-foreground hover:text-destructive"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="border-b border-border/60 pb-2 font-mono text-label uppercase tracking-[0.12em] text-muted-foreground">
        task config
      </div>
      <div className="space-y-3">
        <ProjectSelector
          projects={projects}
          selectedId={selectedProjectId}
          onChange={setSelectedProjectId}
        />
        <div className="border-b border-border/60 pb-2 font-mono text-label uppercase tracking-[0.12em] text-primary">
          run path
        </div>
        <FieldRow label="Working Directory" hint="execution path">
          <input
            value={runPath}
            onChange={(e) => setRunPath(e.target.value)}
            placeholder="/home/runner/..."
            className="w-full border-0 border-b border-border-strong bg-transparent pb-2 font-mono text-data text-foreground focus:border-primary"
          />
        </FieldRow>
        <FieldRow label="name" hint="Task identifier" error={fieldErrors.name}>
          <input
            value={nodeForm.name}
            onChange={(e) => setNodeForm((f) => ({ ...f, name: slugifyTaskName(e.target.value) }))}
            placeholder="Task name"
            className="w-full border-0 border-b border-border-strong bg-transparent pb-2 font-mono text-data text-foreground focus:border-primary"
          />
        </FieldRow>
        <FieldRow label="description" hint="What this task does" error={fieldErrors.description}>
          <input
            value={nodeForm.description}
            onChange={(e) => setNodeForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Describe this task"
            className="w-full border-0 border-b border-border-strong bg-transparent pb-2 font-mono text-data text-foreground focus:border-primary"
          />
        </FieldRow>
        <FieldRow label="task" hint="The command or prompt to run">
          <textarea
            value={nodeForm.task}
            onChange={(e) => setNodeForm((f) => ({ ...f, task: e.target.value }))}
            placeholder="Command or prompt"
            rows={3}
            className="w-full resize-none border border-border/60 bg-transparent p-2 font-mono text-label text-foreground focus:border-primary"
          />
        </FieldRow>
      </div>
    </div>
  );
}
