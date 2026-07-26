import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { GripVertical } from "lucide-react";
import type { Task } from "@/types/task";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { useTaskStore } from "@/runner";
import { toolColor } from "@/constants/tools";
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
    {/* Plain article. It used to carry role="button" + tabIndex={0} while
        containing real <button>s — nested interactive controls, which is
        invalid and made screen readers flatten the whole card into one
        control. The primary action is now one button stretched over the card
        via ::after, so click-anywhere still works while the drag and remove
        buttons sit above it. */}
    <article
      ref={setNodeRef}
      data-testid="task-card"
      data-task-id={task.name}
      data-selected={selected || undefined}
      className={cn(
        "group relative h-[80px] border bg-card px-3 py-2.5 transition-colors hover:border-border/90 focus-within:outline-2 focus-within:outline-primary",
        hitl ? "border-warning border-2 bg-warning/5" : "border-border",
        selected && "border-primary shadow-[0_0_0_1px_var(--color-primary)]",
        task.column === "done" && "bg-transparent",
        isDragging && "opacity-40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 font-mono text-data font-normal leading-snug text-foreground">
          <button
            type="button"
            onClick={onClick}
            className="block w-full truncate text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
          >
            {task.name}
          </button>
        </h3>
        {/* 24px minimum per WCAG 2.5.8; the card is 80px tall, so the 44px of
            2.5.5 (AAA) would not fit alongside the name and description. */}
        <div className="relative z-[1] -mt-1 flex shrink-0 items-center gap-1">
          <button
            type="button"
            {...listeners}
            {...attributes}
            data-testid="drag-handle"
            aria-label={`Drag task ${task.name}`}
            className="flex size-6 cursor-grab items-center justify-center text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-primary"
          >
            <GripVertical className="size-3.5" aria-hidden />
          </button>
          {(task.column === "todo" || task.column === "done") && (
            <button
              type="button"
              onClick={() => setRemoveOpen(true)}
              data-testid="remove-button"
              aria-label="Remove task"
              className="flex h-6 items-center px-1 font-mono text-micro uppercase tracking-[0.12em] text-foreground/50 opacity-0 transition-[opacity,color] group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-primary"
            >
              remove
            </button>
          )}
          {hitl ? (
            <span className="shrink-0 font-mono text-micro uppercase tracking-[0.12em] text-warning">
              waiting for review
            </span>
          ) : (
            <span
              className="shrink-0 font-mono text-micro uppercase tracking-[0.12em]"
              style={{ color: `var(--color-type-${isConduit ? "conduit" : "task"})` }}
            >
              {isConduit ? "conduit" : "task"}
            </span>
          )}
        </div>
      </div>
      {desc && (
        <div className="mt-1 text-body leading-snug text-muted-foreground line-clamp-1">
          {desc}
        </div>
      )}
      {!isConduit && task.tool && (
        <div className="mt-1 flex items-center gap-1.5">
          <span
            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ backgroundColor: toolColor(task.tool) }}
          />
          <span className="font-mono text-micro text-muted-foreground truncate">{task.tool}</span>
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
