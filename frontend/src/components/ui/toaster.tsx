import { Toaster as Sonner } from "sonner";

export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      theme="system"
      toastOptions={{
        classNames: {
          toast:
            "!bg-card !border-border !text-foreground !font-mono !text-xs !rounded-sm !pr-7 !relative group",
          title: "!text-foreground",
          description: "!text-muted-foreground",
          actionButton: "!bg-primary !text-primary-foreground",
          cancelButton: "!text-muted-foreground",
          closeButton:
            "!absolute !right-1.5 !top-1/2 !-translate-y-1/2 !left-auto !border-none !bg-transparent !text-muted-foreground hover:!text-foreground !p-0 !m-0 !w-auto !h-auto [&>svg]:!size-3.5",
        },
      }}
      closeButton
    />
  );
}
