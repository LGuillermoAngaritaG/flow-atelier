import { useEffect, useState } from "react";

// fix footer

function fmtTime(d = new Date()) {
  return d.toTimeString().slice(0, 8);
}

export function Footer() {
  const [now, setNow] = useState(fmtTime);
  useEffect(() => {
    const id = setInterval(() => setNow(fmtTime()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <footer
      data-testid="status-rail"
      className="fixed inset-x-0 bottom-0 z-30 flex h-7 items-center gap-4 border-t border-border bg-background px-6 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
    >
      <span>
        <span className="text-primary">●</span> engine: idle
      </span>
      <span className="opacity-40">│</span>
      <span>seed: 0xA71E · ver 0.1</span>
      <span className="opacity-40">│</span>
      <span>
        running: <span className="text-foreground">2</span>
      </span>
      <span className="opacity-40">│</span>
      <span>need_review: 1</span>
      <span className="ml-auto">{now}</span>
    </footer>
  );
}
