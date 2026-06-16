import type { Conduit } from "@/types/conduit";
import { cn } from "@/lib/cn";

export function ConduitRow({
  conduit,
  idx,
  active,
  onClick,
}: {
  conduit: Conduit;
  idx: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      data-active={active || undefined}
      className={cn(
        "group grid w-full grid-cols-[28px_1fr_auto] items-start gap-4 border-b border-border/50 px-5 py-3.5 text-left last:border-b-0 hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-primary",
        active && "bg-muted/60",
      )}
    >
      <span className="pt-0.5 font-mono text-[10px] text-muted-foreground tabular-nums">
        {String(idx).padStart(2, "0")}
      </span>
      <div className="min-w-0 space-y-1">
        <div
          className={cn(
            "font-mono text-[13px] leading-tight",
            active ? "text-primary" : "text-foreground",
          )}
        >
          {conduit.name}
        </div>
        <div className="text-[12px] text-muted-foreground">
          {conduit.description}
        </div>
      </div>
      <span
        className={cn(
          "shrink-0 whitespace-nowrap pt-0.5 font-mono text-[10px] uppercase tracking-[0.14em]",
          active ? "text-primary" : "text-muted-foreground",
        )}
      >
        {active ? "selected" : `${conduit.tasks.length} tasks`}
      </span>
    </button>
  );
}
