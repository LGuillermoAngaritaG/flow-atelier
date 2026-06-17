export function ProjectSelector({ projects, selectedId, onChange, readOnly, noHint }: {
  projects: Array<{ id: string; name: string }>;
  selectedId: string;
  onChange: (id: string) => void;
  readOnly?: boolean;
  noHint?: boolean;
}) {
  const selected = projects.find((p) => p.id === selectedId);
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-4">
      <div>
        <div id="project-select-label" className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground">
          project
        </div>
        {!noHint && <div className="mt-0.5 text-[11px] text-muted-foreground">assign to project</div>}
      </div>
      {readOnly ? (
        <div className="font-mono text-[13px] text-foreground pb-2">
          {selected?.name ?? selectedId}
        </div>
      ) : (
        <select
          id="project-select"
          value={selectedId}
          onChange={(e) => onChange(e.target.value)}
          aria-labelledby="project-select-label"
          className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      )}
    </div>
  );
}
