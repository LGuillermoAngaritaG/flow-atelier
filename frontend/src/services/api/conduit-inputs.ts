import { CONDUIT_INPUTS_STORAGE_KEY } from "@/constants/dashboard";

// Conduit inputs are free-form and may hold secrets (tokens, passwords). Give
// saved values a lifespan instead of keeping them in localStorage forever, so a
// shared machine doesn't leak them indefinitely. Legacy entries without a
// `savedAt` are treated as expired and silently dropped on read.
const TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

interface StoredEntry {
  inputs: Record<string, string>;
  savedAt: number;
}

function loadAll(): Record<string, StoredEntry> {
  try {
    const raw = localStorage.getItem(CONDUIT_INPUTS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveAll(data: Record<string, StoredEntry>): void {
  localStorage.setItem(CONDUIT_INPUTS_STORAGE_KEY, JSON.stringify(data));
}

export function loadConduitInputs(
  conduitName: string,
): Record<string, string> | null {
  const entry = loadAll()[conduitName];
  if (!entry || typeof entry.savedAt !== "number") return null;
  if (Date.now() - entry.savedAt > TTL_MS) return null;
  return entry.inputs ?? null;
}

export function saveConduitInputs(
  conduitName: string,
  inputs: Record<string, string>,
): void {
  const all = loadAll();
  all[conduitName] = { inputs, savedAt: Date.now() };
  saveAll(all);
}
