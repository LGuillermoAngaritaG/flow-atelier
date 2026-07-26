import type { ReactNode } from "react";
import { TopBar } from "./NavBar";

export function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <TopBar />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
