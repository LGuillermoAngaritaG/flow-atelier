import { useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AppFrame } from "@/layout/AppFrame";
import { ConduitProvider } from "@/services/ConduitProvider";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Toaster } from "@/components/ui/toaster";
import Dashboard from "@/pages/dashboard";
import { Loader2 } from "lucide-react";
import * as runner from "@/runner";

const Designer = lazy(() => import("@/pages/Designer"));
const Kanban = lazy(() => import("@/pages/kanban"));

// Expose runner on window for Playwright smoke checks.
if (typeof window !== "undefined") {
  (window as unknown as { atelier?: typeof runner }).atelier = runner;
}

function ScreenFallback() {
  return (
    <div className="flex items-center justify-center h-full min-h-[200px]">
      <div className="flex flex-col items-center gap-2 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <span className="text-sm">Loading...</span>
      </div>
    </div>
  );
}

export default function App() {
  useEffect(() => {
    runner.bootRunner();
  }, []);
  return (
    <ThemeProvider>
      <ConduitProvider>
        <BrowserRouter>
          <AppFrame>
            <ErrorBoundary>
              <Suspense fallback={<ScreenFallback />}>
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/designer" element={<Designer />} />
                  <Route path="/kanban" element={<Kanban />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </AppFrame>
          <Toaster />
        </BrowserRouter>
      </ConduitProvider>
    </ThemeProvider>
  );
}
