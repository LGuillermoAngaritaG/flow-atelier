import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from "react";
import { fetchConduits, clearConduitCache } from "@/services/conduits";
import { USE_MOCK } from "@/services/client";
import type { Conduit } from "@/types/conduit";

interface ConduitsCtx {
  conduits: Conduit[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const Ctx = createContext<ConduitsCtx>({
  conduits: [],
  loading: true,
  error: null,
  refresh: () => {},
});

export function ConduitProvider({ children }: { children: ReactNode }) {
  const [conduits, setConduits] = useState<Conduit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Tracks whether a load has ever succeeded with data, so the retry timer can
  // stop instead of reading a stale `conduits.length` from its mount closure.
  const loadedRef = useRef(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchConduits()
      .then((data) => {
        setConduits(data);
        setError(null);
        if (data.length > 0) loadedRef.current = true;
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to fetch conduits");
        console.error("[ConduitProvider]", err);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    if (!USE_MOCK) {
      // Retry until the list loads, then stop. ponytail: simple 5s retry; swap
      // for backend push/SSE if conduits ever need live updates after load.
      const id = setInterval(() => {
        if (loadedRef.current) clearInterval(id);
        else load();
      }, 5000);
      return () => clearInterval(id);
    }
  }, [load]);

  const refresh = useCallback(() => {
    clearConduitCache();
    loadedRef.current = false;
    load();
  }, [load]);

  const value = useMemo(
    () => ({ conduits, loading, error, refresh }),
    [conduits, loading, error, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useConduits() {
  return useContext(Ctx);
}

export function getConduitSync(name: string, conduits: Conduit[]): Conduit | undefined {
  return conduits.find((c) => c.name === name);
}
