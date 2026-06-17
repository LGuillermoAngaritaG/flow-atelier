import { type FormEvent, useMemo, useState, useEffect, useCallback } from "react";
import type { Conduit } from "@/types/conduit";
import { hintStr } from "@/types/conduit";
import type { ScheduleConfig } from "@/types/schedule";
import { Button } from "@/components/ui/button";
import { saveConduitInputs, loadConduitInputs } from "@/services/api/conduit-inputs";
import { loadRunPath, saveRunPath } from "@/services/api/conduit-run-path";
import { ScheduleDialog } from "./schedule-dialog";

interface Props {
  conduit: Conduit;
  onRun: (inputs: Record<string, string>, runPath: string) => void;
  onSchedule?: (inputs: Record<string, string>, config: ScheduleConfig, scheduleConduitName?: string, runPath?: string) => void;
}

export function InputForm({ conduit, onRun, onSchedule }: Props) {
  const defaults = useMemo(
    () =>
      Object.fromEntries(
        Object.keys(conduit.inputs).map((name) => [name, ""]),
      ),
    [conduit],
  );

  const [values, setValues] = useState<Record<string, string>>(() => {
    const saved = loadConduitInputs(conduit.name);
    if (saved) {
      const merged = { ...defaults };
      for (const key of Object.keys(defaults)) {
        if (key in saved) merged[key] = saved[key];
      }
      return merged;
    }
    return defaults;
  });
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [runPath, setRunPath] = useState(() =>
    loadRunPath(conduit.name, conduit.runPath ?? ""),
  );

  useEffect(() => {
    const saved = loadConduitInputs(conduit.name);
    if (saved) {
      const merged = { ...defaults };
      for (const key of Object.keys(defaults)) {
        if (key in saved) merged[key] = saved[key];
      }
      setValues(merged);
    } else {
      setValues(defaults);
    }
  }, [conduit.name, defaults]);

  useEffect(() => setRunPath(loadRunPath(conduit.name, conduit.runPath ?? "")), [conduit.name, conduit.runPath]);

  const handleChange = useCallback(
    (name: string, value: string) => {
      setValues((prev) => ({ ...prev, [name]: value }));
    },
    [],
  );

  const handleBlur = useCallback(() => {
    setValues((current) => {
      saveConduitInputs(conduit.name, current);
      return current;
    });
  }, [conduit.name]);

  const handlePathBlur = useCallback(
    (value: string) => {
      setRunPath(value);
      saveRunPath(conduit.name, value);
    },
    [conduit.name],
  );

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!runPath.trim()) errs.runPath = "Working directory is required";
    for (const name of Object.keys(conduit.inputs)) {
      if (!values[name]?.trim()) errs[name] = "Required";
    }
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    onRun(values, runPath);
  };

  return (
    <form onSubmit={submit} data-testid="input-form" className="mt-10">
      <h2 className="sub-title">
      <span className="text-primary">· run path</span>
      </h2>

      <div className="border-t border-border/60">
        <div className="grid grid-cols-[140px_1fr] items-start gap-6 border-b border-border/50 py-4">
          <label htmlFor="run-path" className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground">
            working directory
          </label>
          <div>
            <input
              id="run-path"
              value={runPath}
              onChange={(e) => setRunPath(e.target.value)}
              onBlur={(e) => handlePathBlur(e.target.value)}
              aria-invalid={!!errors.runPath}
              aria-describedby={errors.runPath ? "run-path-error" : undefined}
              className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
              placeholder="/path/to/project"
            />
            {errors.runPath && <div id="run-path-error" className="mt-1 font-mono text-[10px] text-destructive">{errors.runPath}</div>}
          </div>
        </div>
      </div>

      {Object.keys(conduit.inputs).length > 0 && (
      <>
        <h2 className="sub-title mt-8">
        <span className="text-primary">· inputs</span> · {conduit.name}
        </h2>

        <div className="border-t border-border/60">
          {Object.entries(conduit.inputs).map(([name, hint]) => (
          <div
            key={name}
            className="grid grid-cols-[140px_1fr] items-start gap-6 border-b border-border/50 py-4"
          >
            <div>
              <label htmlFor={`input-${name}`} className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground">
                {name}
              </label>
              <div className="mt-1 text-[11px] text-muted-foreground">
                {hintStr(hint)}
              </div>
            </div>
            <div>
              <input
                id={`input-${name}`}
                name={name}
                value={values[name] ?? ""}
                onChange={(e) => handleChange(name, e.target.value)}
                onBlur={handleBlur}
                aria-invalid={!!errors[name]}
                aria-describedby={errors[name] ? `input-${name}-error` : undefined}
                className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
                placeholder={hintStr(hint)}
              />
              {errors[name] && <div id={`input-${name}-error`} className="mt-1 font-mono text-[10px] text-destructive">{errors[name]}</div>}
            </div>
          </div>
        ))}
      </div>
      </>
      )}
      <div className="flex justify-end gap-2 pt-8">
        {onSchedule && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="schedule-conduit"
            onClick={() => setSchedulerOpen(true)}
          >
            ◷ schedule
          </Button>
        )}
        <Button type="submit" size="sm" data-testid="run-conduit">
          ▸ run conduit
        </Button>
      </div>

      {onSchedule && (
        <ScheduleDialog
          conduitName={conduit.name}
          defaultInputs={values}
          defaultRunPath={runPath}
          open={schedulerOpen}
          onOpenChange={setSchedulerOpen}
          onConfirm={(config, conduitName, inputs, runPath) => onSchedule(inputs, config, conduitName, runPath)}
        />
      )}
    </form>
  );
}
