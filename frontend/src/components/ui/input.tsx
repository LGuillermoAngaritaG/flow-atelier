import * as React from "react";
import { cn } from "@lib/cn";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "flex h-9 w-full rounded-sm border border-border bg-transparent px-3 py-1 font-mono text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
