import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cn } from "@lib/cn";

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(
      "text-[11px] font-mono uppercase tracking-[0.12em] text-muted-foreground",
      className,
    )}
    {...props}
  />
));
Label.displayName = "Label";
