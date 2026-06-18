import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (name: string) => void;
}

export function NewProjectDialog({ open, onOpenChange, onCreate }: Props) {
  const [name, setName] = useState("");

  useEffect(() => {
    if (!open) setName("");
  }, [open]);

  const submit = () => {
    const trimmed = name.trim().slice(0, 32);
    if (!trimmed) return;
    onCreate(trimmed);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            <em className="text-primary not-italic">new project</em>
          </DialogTitle>
          <DialogDescription>create a new project to organize your tasks</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[100px_1fr] items-start gap-4">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground">
              name
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">project name</div>
          </div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            placeholder="my project"
            autoFocus
            className="w-full border-0 border-b border-border bg-transparent pb-2 font-mono text-[13px] text-foreground outline-none focus:border-primary"
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            cancel
          </Button>
          <Button type="button" size="sm" onClick={submit} disabled={!name.trim()}>
            create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
