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

type Step = "confirm" | "danger";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectName: string;
  hasHistory: boolean;
  onConfirm: () => void;
}

export function DeleteProjectDialog({ open, onOpenChange, projectName, hasHistory, onConfirm }: Props) {
  const [step, setStep] = useState<Step>("confirm");

  useEffect(() => {
    if (!open) setStep("confirm");
  }, [open]);

  const handleFirstConfirm = () => {
    if (hasHistory) {
      setStep("danger");
    } else {
      onConfirm();
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        {step === "confirm" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                delete <em className="text-primary not-italic italic">{projectName}</em>?
              </DialogTitle>
              <DialogDescription>
                Are you sure you want to delete this project?
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                cancel
              </Button>
              <Button type="button" variant="destructive" size="sm" onClick={handleFirstConfirm}>
                delete
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>
                this cannot be <em className="text-destructive not-italic italic">undone</em>
              </DialogTitle>
              <DialogDescription>
                Your completed flows will be removed if you delete this project.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => {
                  onConfirm();
                  onOpenChange(false);
                }}
              >
                permanently delete
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
