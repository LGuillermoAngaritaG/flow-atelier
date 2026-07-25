export function FieldRow({ label, hint, error, children }: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  // Label stacks above the field below sm; the fixed 140px column used to
  // apply at every width and squeezed the input on a phone.
  return (
    <div className="grid grid-cols-1 items-start gap-1 sm:grid-cols-[140px_1fr] sm:gap-4">
      <div>
        <div className="font-mono text-label uppercase tracking-[0.12em] text-foreground">{label}</div>
        {hint && <div className="mt-0.5 text-label text-muted-foreground">{hint}</div>}
      </div>
      <div>
        {children}
        {error && <div className="mt-1 font-mono text-mini text-destructive">{error}</div>}
      </div>
    </div>
  );
}
