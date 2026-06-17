import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import type { Task } from "@/types/task";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { useTaskStore } from "@/runner";
import { TOOL_COLORS } from "../toolMeta";
import { cn } from "@/lib/cn";
import { RemoveTaskDialog } from "./RemoveTaskDialog";

interface Props {
  task: Task;
  selected?: boolean;
  onClick?: () => void;
}

export function TaskCard({ task, selected, onClick }: Props) {
  const { conduits } = useConduits();
  const conduit = getConduitSync(task.name, conduits);
  const isConduit = !!conduit;
  const hitl = task.flow?.hitlRequest;
  const desc = task.description ?? conduit?.description;
  const [removeOpen, setRemoveOpen] = useState(false);
  const handleDelete = () => useTaskStore.getState().remove(task.name);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `task-${task.name}`,
    data: { column: task.column, taskName: task.name },
  });

  return (
    <>
    <article
      ref={setNodeRef}
      data-testid="task-card"
      data-task-id={task.name}
      data-selected={selected || undefined}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      className={cn(
        "group h-[80px] border bg-card px-3 py-2.5 transition-colors hover:border-border/90 focus-visible:outline-2 focus-visible:outline-primary",
        hitl ? "border-orange-500 border-2 bg-orange-500/5" : "border-border",
        selected && "border-primary shadow-[0_0_0_1px_var(--color-primary)]",
        task.column === "done" && "bg-transparent",
        isDragging && "opacity-40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 font-mono text-[14px] leading-snug text-foreground  line-clamp-1">
          {task.name}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            {...listeners}
            {...attributes}
            onClick={(e) => e.stopPropagation()}
            data-testid="drag-handle"
            aria-label={`Drag task ${task.name}`}
            className="cursor-grab font-mono text-[11px] leading-none text-foreground/40 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-primary"
          >
            ⠿
          </button>
          {(task.column === "todo" || task.column === "done") && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setRemoveOpen(true); }}
              data-testid="remove-button"
              aria-label="Remove task"
              className="opacity-0 font-mono text-[9px] uppercase tracking-[0.12em] text-foreground/50 transition-[opacity,color] group-hover:opacity-100 hover:text-destructive focus:opacity-100"
            >
              remove
            </button>
          )}
          {hitl ? (
            <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.12em] text-orange-500">
              waiting for review
            </span>
          ) : (
            <span
              className="shrink-0 font-mono text-[9px] uppercase tracking-[0.12em]"
              style={{ color: `var(--color-type-${isConduit ? "conduit" : "task"})` }}
            >
              {isConduit ? "conduit" : "task"}
            </span>
          )}
        </div>
      </div>
      {desc && (
        <div className="mt-1 text-[12px] leading-snug text-muted-foreground line-clamp-1">
          {desc}
        </div>
      )}
      {!isConduit && task.tool && (
        <div className="mt-1 flex items-center gap-1.5">
          <span
            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ backgroundColor: TOOL_COLORS[task.tool] ?? "var(--color-muted-foreground)" }}
          />
          <span className="font-mono text-[9px] text-muted-foreground/70 truncate">{task.tool}</span>
        </div>
      )}
    </article>
    <RemoveTaskDialog
      open={removeOpen}
      onOpenChange={setRemoveOpen}
      taskName={task.name}
      onConfirm={handleDelete}
    />
    </>
  );
}
