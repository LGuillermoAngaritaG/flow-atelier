import { useState, useEffect } from "react";
import { toast } from "sonner";
import { ConduitPicker } from "@/features/dashboard/components/conduit-picker";
import { InputForm } from "@/features/dashboard/components/input-form";
import { FlowHistory } from "@/features/dashboard/components/flow-history";
import { Button } from "@/components/ui/button";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { useConduit } from "@/hooks/useConduit";
import { fetchSchedules } from "@/services/conduits";
import { createSchedule, deleteSchedule } from "@/services/api/schedules";
import { ScheduleDialog } from "@/features/dashboard/components/schedule-dialog";
import type { ScheduleConfig, ScheduledJob } from "@/types/schedule";

export default function Dashboard() {
  const { conduits, loading, error, refresh } = useConduits();
  const [selected, setSelected] = useState(conduits[0]?.name ?? "");
  const [scheduledJobs, setScheduledJobs] = useState<ScheduledJob[]>([]);
  const [addScheduleOpen, setAddScheduleOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const conduit = getConduitSync(selected, conduits) ?? conduits[0];

  const { run, cancel, resume, answerHITL, liveRuns } = useConduit({
    onFlowComplete: () => {
      setRefreshKey((k) => k + 1);
    },
  });

  const refreshAll = () => {
    setRefreshKey((k) => k + 1);
    fetchSchedules().then(setScheduledJobs).catch(() => toast.error("Failed to load schedules"));
  };

  useEffect(() => {
    let ignore = false;
    fetchSchedules()
      .then((jobs) => {
        if (!ignore) setScheduledJobs(jobs);
      })
      .catch(() => {
        if (!ignore) toast.error("Failed to load schedules");
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (conduits.length > 0 && !conduits.find((c) => c.name === selected)) {
      setSelected(conduits[0].name);
    }
  }, [conduits, selected]);

  const handleSchedule = (inputs: Record<string, string>, config: ScheduleConfig, scheduleConduitName?: string, runPath?: string) => {
    const conduitName = scheduleConduitName ?? conduit.name;

    createSchedule({
      conduitName,
      inputs,
      runPath,
      schedule: config,
    })
      .then((job) => {
        setScheduledJobs((prev) => [job, ...prev]);
        refreshAll();
        toast.success(`Scheduled ${job.schedule.name || conduitName}`);
      })
      .catch((e) => {
        toast.error(e instanceof Error ? e.message : "Failed to create schedule");
      });
  };

  const handleDeleteJob = (id: string) => {
    const job = scheduledJobs.find((j) => j.id === id);
    deleteSchedule(id).then(() => {
      setScheduledJobs((prev) => prev.filter((j) => j.id !== id));
      refreshAll();
      toast.success(`Deleted schedule ${job?.schedule.name || job?.conduitName || ""}`);
    }).catch(() => {
      toast.error("Failed to delete schedule");
    });
  };

  const handleRun = (inputs: Record<string, string>, runPath: string) => {
    run(conduit.name, inputs, runPath);
    toast.success(`Started ${conduit.name}`);
  };

  const handleResume = (flowId: string, conduitName?: string) => {
    resume(flowId, conduitName);
    toast.success("Resuming flow");
  };

  return (
    <div data-route="dashboard" className="min-h-[calc(100vh-3.5rem-1.75rem)]">
      <section
        data-testid="dashboard-main"
        className="px-10 py-10"
      >
        <header className="mb-10 flex items-baseline justify-between gap-10 border-b border-border pb-7">
          <h1 className="page-title">
            Run a <em className="text-primary not-italic">conduit</em>
          </h1>
          <div className="text-right font-mono text-[11px] uppercase tracking-[0.12em] leading-relaxed text-muted-foreground">
            {loading ? "loading…" : `${conduits.length} conduits`}
          </div>
        </header>

        {error ? (
          <div data-testid="dashboard-error" className="mx-auto max-w-[560px] py-20 text-center">
            <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.12em] text-destructive">
              Failed to load conduits
            </div>
            <div className="mb-6 font-mono text-[11px] text-muted-foreground">{error}</div>
            <Button variant="outline" size="sm" onClick={refresh}>
              retry
            </Button>
          </div>
        ) : loading ? (
          <div data-testid="dashboard-loading" className="mx-auto grid max-w-[1280px] grid-cols-1 gap-16 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
            <section>
              <div className="space-y-3">
                <div className="h-4 w-28 animate-pulse rounded bg-muted" />
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-12 animate-pulse rounded-sm border border-border bg-muted/40" />
                ))}
              </div>
              <div className="mt-10 space-y-4">
                <div className="h-4 w-20 animate-pulse rounded bg-muted" />
                {[1, 2].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded-sm border border-border bg-muted/40" />
                ))}
              </div>
            </section>
            <section>
              <div className="space-y-3">
                <div className="h-4 w-32 animate-pulse rounded bg-muted" />
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 animate-pulse rounded-sm border border-border bg-muted/40" />
                ))}
              </div>
            </section>
          </div>
        ) : (
        <div className="mx-auto grid max-w-[1280px] grid-cols-1 gap-16 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <section>
            <ConduitPicker selected={selected} onSelect={setSelected} />
            {conduit && (
              <InputForm conduit={conduit} onRun={handleRun} onSchedule={handleSchedule} />
            )}
          </section>
          <section>
            <FlowHistory
              scheduledJobs={scheduledJobs}
              onDeleteJob={handleDeleteJob}
              onAddSchedule={() => setAddScheduleOpen(true)}
              refreshKey={refreshKey}
              liveRuns={liveRuns}
              onRespondToHitl={answerHITL}
              onCancelRun={cancel}
              onResumeRun={handleResume}
            />
          </section>
        </div>
        )}
      </section>

      <ScheduleDialog
        conduitName=""
        open={addScheduleOpen}
        onOpenChange={setAddScheduleOpen}
        onConfirm={(config, name, inputs, runPath) => handleSchedule(inputs, config, name, runPath)}
      />
    </div>
  );
}
