import { useConduits } from "@/services/ConduitProvider";
import type { Conduit } from "@/types/conduit";
import { hintStr } from "@/types/conduit";
import { cn } from "@/lib/cn";
import { FieldRow } from "./FieldRow";
import { ProjectSelector } from "./ProjectSelector";

interface Props {
  step: "conduit-select" | "conduit-inputs";
  conduit: Conduit;
  selectedConduit: string;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  runPath: string;
  setRunPath: (v: string) => void;
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
  projects: Array<{ id: string; name: string }>;
  selectConduitAndAdvance: (name: string) => void;
}

export function ConduitFlow({
  step,
  conduit,
  selectedConduit,
  values,
  setValues,
  runPath,
  setRunPath,
  selectedProjectId,
  setSelectedProjectId,
  projects,
  selectConduitAndAdvance,
}: Props) {
  const { conduits } = useConduits();
  if (step === "conduit-select") {
    return (
      <div className="max-h-80 overflow-auto border border-border">
        {conduits.map((c, i) => (
          <button
            key={c.name}
            type="button"
            onClick={() => selectConduitAndAdvance(c.name)}
            className={cn(
              "grid w-full grid-cols-[28px_1fr_auto] items-start gap-4 border-b border-border/50 px-4 py-3 text-left font-mono text-[12px] last:border-b-0 hover:bg-muted/40",
              selectedConduit === c.name && "bg-muted/60",
            )}
          >
            <span className="font-mono text-[10px] text-muted-foreground tabular-nums">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0">
              <div className={cn("text-[13px]", selectedConduit === c.name ? "text-primary" : "text-foreground")}>
                {c.name}
              </div>
              <div className="text-[11px] text-muted-foreground">{c.description}</div>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {c.tasks.length} tasks
            </span>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <ProjectSelector
        projects={projects}
        selectedId={selectedProjectId}
        onChange={setSelectedProjectId}
      />
      <div className="border-b border-border/60 pb-2 font-mono text-[11px] uppercase tracking-[0.12em] text-primary">
        run path
      </div>
      <FieldRow label="Working Directory" hint="execution path">
        <input
          value={runPath}
          onChange={(e) => setRunPath(e.target.value)}
          placeholder="/home/runner/..."
          className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
        />
      </FieldRow>
      {Object.entries(conduit.inputs).length > 0 && (
        <>
          <div className="border-b border-border/60 pb-2 font-mono text-[11px] uppercase tracking-[0.12em] text-primary">
            inputs
          </div>
          {Object.entries(conduit.inputs).map(([name, hint]) => (
            <FieldRow key={name} label={name} hint={hintStr(hint)}>
              <input
                value={values[name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
                placeholder={hintStr(hint)}
                className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
              />
            </FieldRow>
          ))}
        </>
      )}
    </div>
  );
}
