import { useState } from "react";
import { DateRange, DayPicker } from "react-day-picker";
import { format } from "date-fns";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

import "react-day-picker/style.css";

interface Props {
  from: string;
  to: string;
  onConfirm: (from: string, to: string) => void;
}

export function DateRangePicker({ from, to, onConfirm }: Props) {
  const [open, setOpen] = useState(true);
  const [draft, setDraft] = useState<DateRange | undefined>(() =>
    from ? { from: parseLocal(from), to: to ? parseLocal(to) : undefined } : undefined,
  );

  const confirmed: DateRange | undefined = from
    ? { from: parseLocal(from), to: to ? parseLocal(to) : undefined }
    : undefined;

  const hasConfirmed = confirmed?.from && confirmed?.to;
  const hasDraft = draft?.from && draft?.to;

  const label = hasConfirmed
    ? `${format(confirmed.from!, "MMM d")} → ${format(confirmed.to!, "MMM d")}`
    : "pick dates";

  function handleDone() {
    if (!hasDraft) return;
    onConfirm(fmt(draft!.from!), fmt(draft!.to!));
    setOpen(false);
  }

  function handleClear() {
    setDraft(undefined);
    onConfirm("", "");
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "h-7 cursor-pointer rounded border px-2 font-mono text-[12px] outline-none focus:border-primary",
            hasConfirmed ? "border-primary text-primary" : "border-border text-foreground",
            "bg-background",
          )}
        >
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-3">
        <DayPicker
          mode="range"
          selected={draft}
          onSelect={setDraft}
          numberOfMonths={1}
          disabled={{ after: new Date() }}
        />
        <div className="mt-3 flex items-center justify-between border-t border-border pt-2">
          <button
            type="button"
            onClick={handleClear}
            className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground"
          >
            clear
          </button>
          <Button
            type="button"
            size="sm"
            disabled={!hasDraft}
            onClick={handleDone}
          >
            done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function parseLocal(dateStr: string): Date {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function fmt(d: Date): string {
  return format(d, "yyyy-MM-dd");
}
