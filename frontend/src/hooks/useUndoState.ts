import { useState, useCallback, useRef } from "react";

const MAX_HISTORY = 50;
const DEBOUNCE_MS = 400;

/**
 * Wraps useState with Ctrl+Z–friendly undo.
 * Rapid setter calls (e.g. text typing) are debounced into one history entry.
 */
export function useUndoState<T>(initial: T | (() => T)) {
  const [state, setStateRaw] = useState(initial);

  const history = useRef<T[]>([]);
  const future = useRef<T[]>([]);
  const pending = useRef<T | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const flush = useCallback(() => {
    if (pending.current !== null) {
      history.current.push(pending.current);
      if (history.current.length > MAX_HISTORY) history.current.shift();
      pending.current = null;
    }
  }, []);

  const setState = useCallback(
    (value: T | ((prev: T) => T)) => {
      setStateRaw((prev) => {
        const next =
          typeof value === "function"
            ? (value as (p: T) => T)(prev)
            : value;

        future.current = [];

        // First mutation in a burst captures the pre-mutation state
        if (pending.current === null) pending.current = structuredClone(prev);

        clearTimeout(timer.current);
        timer.current = setTimeout(flush, DEBOUNCE_MS);
        return next;
      });
    },
    [flush],
  );

  const undo = useCallback(() => {
    clearTimeout(timer.current);
    pending.current = null;
    if (history.current.length === 0) return;
    setStateRaw((prev) => {
      future.current.push(prev);
      return history.current.pop()!;
    });
  }, []);

  const redo = useCallback(() => {
    if (future.current.length === 0) return;
    clearTimeout(timer.current);
    pending.current = null;
    setStateRaw((prev) => {
      const next = future.current.pop()!;
      history.current.push(prev);
      if (history.current.length > MAX_HISTORY) history.current.shift();
      return next;
    });
  }, []);

  return [state, setState, undo, redo] as const;
}
