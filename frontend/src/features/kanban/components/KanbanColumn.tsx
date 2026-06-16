import { useState, useLayoutEffect, useRef } from "react";
import { useDroppable } from "@dnd-kit/core";
import { KANBAN_SCROLL_THRESHOLD } from "@/constants/kanban";
import type { ReactNode } from "react";
import type { ColumnId } from "@/types/task";

interface Props {
  id: ColumnId;
  title: string;
  count: number;
  children: ReactNode;
  onAdd?: () => void;
}

export function KanbanColumn({ id, title, count, children, onAdd }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const [cardHeight, setCardHeight] = useState(0);
  const { setNodeRef, isOver } = useDroppable({ id });

  useLayoutEffect(() => {
    const first = listRef.current?.firstElementChild as HTMLElement | null;
    if (first) setCardHeight(first.offsetHeight);
  }, [count]);

  const constrainedHeight =
    count > KANBAN_SCROLL_THRESHOLD && cardHeight > 0
      ? cardHeight * KANBAN_SCROLL_THRESHOLD
      : undefined;

  return (
    <section
      ref={setNodeRef}
      data-testid={`column-${id}`}
      data-column={id}
      className={`flex min-w-0 flex-col transition-colors ${isOver ? "bg-primary/5" : ""}`}
    >
      <header className="flex items-baseline justify-between border-b border-border pb-2 ">
        <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted-foreground">
          {title}
          <span className="ml-2 tabular-nums text-muted-foreground/60">
            {count.toString().padStart(2, "0")}
          </span>
        </span>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            aria-label={`Add task to ${title}`}
            className="font-mono text-[12px] uppercase tracking-[0.14em] leading-none text-muted-foreground hover:text-primary"
          >
            + add
          </button>
        )}
      </header>
      <div
        className="mt-2 overflow-y-auto pr-3"
        style={constrainedHeight ? { maxHeight: constrainedHeight } : undefined}
      >
        <div ref={listRef} className="flex flex-col gap-2 pr-1">
          {children}
        </div>
      </div>
    </section>
  );
}
