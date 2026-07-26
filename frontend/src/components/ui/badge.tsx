import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@lib/cn";

const badgeVariants = cva(
  "inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-mini uppercase tracking-[0.12em]",
  {
    variants: {
      variant: {
        default: "border-border bg-muted text-foreground",
        primary: "border-primary/40 bg-primary/15 text-primary",
        ok: "border-transparent bg-[color:var(--color-ok)]/20 text-[color:var(--color-ok)]",
        destructive:
          "border-destructive/40 bg-destructive/15 text-destructive",
        outline: "border-border bg-transparent text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
