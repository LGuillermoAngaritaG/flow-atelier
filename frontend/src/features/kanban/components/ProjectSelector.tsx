import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function ProjectSelector({ projects, selectedId, onChange, readOnly, noHint }: {
  projects: Array<{ id: string; name: string }>;
  selectedId: string;
  onChange: (id: string) => void;
  readOnly?: boolean;
  noHint?: boolean;
}) {
  const selected = projects.find((p) => p.id === selectedId);
  return (
    <div className="grid grid-cols-1 items-start gap-1 sm:grid-cols-[140px_1fr] sm:gap-4">
      <div>
        <div id="project-select-label" className="font-mono text-label uppercase tracking-[0.12em] text-foreground">
          project
        </div>
        {!noHint && <div className="mt-0.5 text-label text-muted-foreground">assign to project</div>}
      </div>
      {readOnly ? (
        <div className="font-mono text-data text-foreground pb-2">
          {selected?.name ?? selectedId}
        </div>
      ) : (
        <Select value={selectedId} onValueChange={onChange}>
          <SelectTrigger
            id="project-select"
            aria-labelledby="project-select-label"
            className="text-data"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
