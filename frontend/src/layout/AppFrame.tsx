import type { ReactNode } from "react";
import { TopBar } from "./NavBar";
// Footer disabled — will be re-enabled when status rail is needed
// import { Footer } from "./Footer";

export function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background text-foreground">
      <TopBar />
      <main className="flex-1 overflow-y-auto">{children}</main>
      {/* <Footer /> */}
    </div>
  );
}
