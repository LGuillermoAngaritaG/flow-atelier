import { useEffect } from "react";

export type EdgeKind = "depends_on" | "match" | "not_match";

const OPTIONS: { value: EdgeKind; label: string }[] = [
  { value: "depends_on", label: "depends on" },
  { value: "match", label: "match" },
  { value: "not_match", label: "not match" },
];

interface EdgeTypePopupProps {
  x: number;
  y: number;
  current?: EdgeKind;
  onSelect: (kind: EdgeKind) => void;
  onRemove: () => void;
  onClose: () => void;
}

export function EdgeTypePopup({ x, y, current, onSelect, onRemove, onClose }: EdgeTypePopupProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        onClick={onClose}
        onContextMenu={(e) => { e.preventDefault(); onClose(); }}
      />
      <div
        className="fixed z-50 flex flex-col rounded border border-border bg-card shadow-md"
        style={{ left: x, top: y }}
      >
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onSelect(opt.value)}
            className={
              "px-3 py-1.5 text-left font-mono text-[10px] uppercase tracking-[0.1em] transition-colors hover:bg-accent " +
              (opt.value === current ? "text-primary font-bold" : "text-foreground")
            }
          >
            {opt.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onRemove()}
          className="border-t border-border px-3 py-1.5 text-left font-mono text-[10px] uppercase tracking-[0.1em] text-destructive transition-colors hover:bg-accent"
        >
          remove
        </button>
      </div>
    </>
  );
}
