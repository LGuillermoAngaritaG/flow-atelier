import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AppFrame } from "@/layout/AppFrame";
import { ConduitProvider } from "@/services/ConduitProvider";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Toaster } from "@/components/ui/toaster";
import Dashboard from "@/pages/dashboard";
import Designer from "@/pages/Designer";
import Kanban from "@/pages/kanban";
import * as runner from "@/runner";

// Expose runner on window for Playwright smoke checks.
if (typeof window !== "undefined") {
  (window as unknown as { atelier?: typeof runner }).atelier = runner;
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
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/designer" element={<Designer />} />
                <Route path="/kanban" element={<Kanban />} />
              </Routes>
            </ErrorBoundary>
          </AppFrame>
          <Toaster />
        </BrowserRouter>
      </ConduitProvider>
    </ThemeProvider>
  );
}
