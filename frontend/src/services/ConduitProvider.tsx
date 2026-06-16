import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
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

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchConduits()
      .then((data) => {
        setConduits(data);
        setError(null);
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
      const id = setInterval(() => {
        if (conduits.length === 0) load();
      }, 5000);
      return () => clearInterval(id);
    }
  }, []);

  const refresh = () => {
    clearConduitCache();
    load();
  };

  return (
    <Ctx.Provider value={{ conduits, loading, error, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export function useConduits() {
  return useContext(Ctx);
}

export function getConduitSync(name: string, conduits: Conduit[]): Conduit | undefined {
  return conduits.find((c) => c.name === name);
}
