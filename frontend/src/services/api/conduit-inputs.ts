import { CONDUIT_INPUTS_STORAGE_KEY } from "@/constants/dashboard";

function loadAll(): Record<string, Record<string, string>> {
  try {
    const raw = localStorage.getItem(CONDUIT_INPUTS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveAll(data: Record<string, Record<string, string>>): void {
  localStorage.setItem(CONDUIT_INPUTS_STORAGE_KEY, JSON.stringify(data));
}

export function loadConduitInputs(
  conduitName: string,
): Record<string, string> | null {
  return loadAll()[conduitName] ?? null;
}

export function saveConduitInputs(
  conduitName: string,
  inputs: Record<string, string>,
): void {
  const all = loadAll();
  all[conduitName] = inputs;
  saveAll(all);
}
