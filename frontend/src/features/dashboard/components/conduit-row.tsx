import type { Conduit } from "@/types/conduit";
import { cn } from "@/lib/cn";

export function ConduitRow({
  conduit,
  active,
  onClick,
}: {
  conduit: Conduit;
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
        // The leading 01/02/03 column is gone: conduits have no order, so the
        // index carried no information the reader could use.
        "group grid w-full grid-cols-[1fr_auto] items-start gap-4 border-b border-border/50 px-4 py-3.5 text-left last:border-b-0 hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-primary sm:px-5",
        active && "bg-muted/60",
      )}
    >
      <div className="min-w-0 space-y-1">
        <div
          className={cn(
            "font-mono text-data leading-tight",
            active ? "text-primary" : "text-foreground",
          )}
        >
          {conduit.name}
        </div>
        <div className="text-body leading-snug text-muted-foreground">
          {conduit.description}
        </div>
      </div>
      {/* "selected" used to replace the task count, so you lost the count at
          exactly the moment you were deciding whether to run it. */}
      <span
        className={cn(
          "shrink-0 whitespace-nowrap pt-0.5 text-right font-mono text-mini uppercase tracking-[0.14em]",
          active ? "text-primary" : "text-muted-foreground",
        )}
      >
        {conduit.tasks.length} tasks
        {active && <span className="mt-0.5 block text-primary">selected</span>}
      </span>
    </button>
  );
}
