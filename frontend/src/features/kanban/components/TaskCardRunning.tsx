import { useEffect, useRef } from "react";
import type { Task } from "@/types/task";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { cancelTask as cancelEngine } from "@/runner";
import { TOOL_COLORS } from "../toolMeta";
import { cn } from "@/lib/cn";

interface Props {
  task: Task;
  selected?: boolean;
  onClick?: () => void;
}

export function TaskCardRunning({ task, selected, onClick }: Props) {
  const { conduits } = useConduits();
  const conduit = getConduitSync(task.name, conduits);
  const isConduit = !!conduit;
  const desc = task.description ?? conduit?.description;
  const flow = task.flow!;
  const order = conduit?.tasks ?? [];
  const doneCount = order.filter(
    (t) => flow.taskStatuses[t.name] === "done",
  ).length;
  const pct = order.length ? (doneCount / order.length) * 100 : 0;
  const hitl = flow.hitlRequest;

  const logsRef = useRef<HTMLDivElement>(null);
  const tail = flow.logLines.slice(-4);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [tail.length]);

  return (
    <article
      data-testid="task-card-running"
      data-task-id={task.name}
      data-selected={selected || undefined}
      onClick={onClick}
      className={cn(
        "group min-w-0 overflow-hidden cursor-pointer border bg-card px-3 py-2.5",
        hitl ? "border-orange-500 border-2 bg-orange-500/5" : "border-border",
        selected && "border-primary shadow-[0_0_0_1px_var(--color-primary)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 font-mono text-[14px] leading-snug text-foreground truncate">
          {task.name}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); cancelEngine(task.name); }}
            data-testid="cancel-button"
            aria-label="Cancel task"
            className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground hover:text-destructive"
          >
            cancel
          </button>
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
        <div className="mt-0.5 text-[12px] leading-snug text-muted-foreground truncate">
          {desc}
        </div>
      )}
      {!isConduit && task.tool && (
        <div className="mt-0.5 flex items-center gap-1.5">
          <span
            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ backgroundColor: TOOL_COLORS[task.tool] ?? "var(--color-muted-foreground)" }}
          />
          <span className="font-mono text-[9px] text-muted-foreground/70 truncate">{task.tool}</span>
        </div>
      )}

      <div className="mt-2 h-[2px] bg-border/60">
        <div
          className="h-full bg-primary transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
        <span>{doneCount}/{order.length}</span>
        <span className="flex items-center gap-1">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/50 motion-reduce:hidden" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
          </span>
          live
        </span>
      </div>

      <div
        ref={logsRef}
        className="relative mt-2 max-h-[68px] overflow-hidden border border-border/60 bg-background px-2 py-1.5 font-mono text-[9px] leading-[1.5] text-muted-foreground"
      >
        {tail.map((line, i) => (
          <div
            key={i}
            className={cn(
              "truncate",
              line.level === "ok" && "text-[color:var(--color-ok)]",
              line.level === "acc" && "text-primary",
              line.level === "err" && "text-destructive",
            )}
          >
            {line.text}
          </div>
        ))}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-5 bg-gradient-to-t from-card to-transparent" />
      </div>
    </article>
  );
}
