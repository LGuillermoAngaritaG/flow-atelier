import { useState } from "react";
import type { ScheduledJob } from "@/types/schedule";
import { cn } from "@/lib/cn";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import { FLOW_HISTORY_SCROLL_THRESHOLD } from "@/constants/dashboard";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

interface Props {
  jobs: ScheduledJob[];
  onDelete?: (id: string) => void;
  onAdd?: () => void;
}

const DAY_LABELS = ["", "mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function fmtDays(job: ScheduledJob): string {
  const { schedule } = job;
  if (schedule.mode === "once") {
    if (!schedule.runAt) return "once";
    const d = new Date(schedule.runAt);
    return d.toLocaleDateString([], {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  const dayStr = schedule.days?.map((d) => DAY_LABELS[d]).join(", ") ?? "";
  const timeStr = schedule.times?.join(", ") ?? "";
  return [dayStr, timeStr].filter(Boolean).join(" · ");
}

export function ScheduledJobs({ jobs, onDelete, onAdd }: Props) {
  const [pendingDelete, setPendingDelete] = useState<ScheduledJob | null>(null);
  const needsScroll = jobs.length > FLOW_HISTORY_SCROLL_THRESHOLD;

  return (
    <div>
      {onAdd && (
        <div className="flex justify-end mb-3">
          <Button variant="outline" size="sm" onClick={onAdd}>
            + add
          </Button>
        </div>
      )}

      <ScrollArea
        style={
          needsScroll
            ? { height: FLOW_HISTORY_SCROLL_THRESHOLD * 52 }
            : undefined
        }
      >
        <ul className="divide-y divide-border/60">
          {jobs.length === 0 && (
            <li className="py-8 text-center font-mono text-[12px] text-muted-foreground">
              no scheduled jobs
            </li>
          )}
          {jobs.map((job) => (
            <li
              key={job.id}
              data-testid="scheduled-job-row"
              data-status={job.status}
              className="py-3"
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={cn(
                    "shrink-0 h-2 w-2 rounded-full",
                    job.schedule.mode === "once" && job.runsCompleted > 0
                      ? "bg-[color:var(--color-ok)]"
                      : "bg-muted-foreground/50",
                  )}
                />
                <span className="truncate font-mono text-[12px] text-foreground">
                  {job.schedule.name || job.conduitName}
                </span>
                <span
                  className={cn(
                    "shrink-0 font-mono text-[9px] uppercase tracking-[0.12em]",
                    job.schedule.mode === "once" && job.runsCompleted > 0
                      ? "text-[color:var(--color-ok)]/60"
                      : "text-muted-foreground",
                  )}
                >
                  {job.schedule.mode === "once"
                    ? job.runsCompleted > 0 ? "ran" : "pending"
                    : "recurring"}
                </span>
                {onDelete && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`delete schedule ${job.schedule.name || job.conduitName}`}
                    className="ml-auto h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => setPendingDelete(job)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
              <div className="mt-0.5 truncate pl-4 text-[11px] text-muted-foreground">
                {fmtDays(job)}
              </div>
            </li>
          ))}
        </ul>
      </ScrollArea>

      <Dialog open={!!pendingDelete} onOpenChange={(open) => { if (!open) setPendingDelete(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>delete schedule</DialogTitle>
            <DialogDescription>
              delete{" "}
              <span className="font-mono text-foreground">
                {pendingDelete?.schedule.name || pendingDelete?.conduitName}
              </span>
              ? this cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setPendingDelete(null)}>
              cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (pendingDelete) onDelete?.(pendingDelete.id);
                setPendingDelete(null);
              }}
            >
              delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
