import type { Conduit } from "@/types/conduit";

interface Props {
  conduits: Conduit[];
  activeName: string;
  onSelect: (name: string) => void;
}

export function ConduitList({ conduits, activeName, onSelect }: Props) {
  return (
    <aside
      data-testid="designer-conduit-list"
      className="w-[220px] shrink-0 overflow-auto border-r border-border bg-background py-7"
    >
      <div className="px-5 pb-5">
        <span className="font-mono text-micro uppercase tracking-[0.18em] text-muted-foreground">
          conduits
        </span>
      </div>
      <div className="flex flex-col gap-1.5 px-3">
        {conduits.map((c) => {
          const isActive = c.name === activeName;
          return (
            <button
              key={c.name}
              type="button"
              onClick={() => onSelect(c.name)}
              className={`w-full rounded-md border px-3 py-2.5 text-left transition-colors ${
                isActive
                  ? "border-primary/50 bg-primary/8"
                  : "border-border/50 hover:border-border hover:bg-muted/40"
              }`}
            >
              <div
                className={`font-mono text-label leading-tight ${
                  isActive ? "text-primary" : "text-foreground"
                }`}
              >
                {c.name}
              </div>
              {c.description && (
                <div className="mt-1 truncate text-mini leading-snug text-muted-foreground">
                  {c.description}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
