export function FieldRow({ label, hint, error, children }: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-4">
      <div>
        <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground">{label}</div>
        {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
      </div>
      <div>
        {children}
        {error && <div className="mt-1 font-mono text-[10px] text-destructive">{error}</div>}
      </div>
    </div>
  );
}
