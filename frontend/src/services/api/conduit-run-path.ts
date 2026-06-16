import { CONDUIT_RUN_PATHS_STORAGE_KEY } from "@/constants/dashboard";

function loadAll(): Record<string, string> {
  try {
    const raw = localStorage.getItem(CONDUIT_RUN_PATHS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function loadRunPath(
  conduitName: string,
  fallback: string,
): string {
  return loadAll()[conduitName] ?? fallback;
}

export function saveRunPath(
  conduitName: string,
  runPath: string,
): void {
  const all = loadAll();
  all[conduitName] = runPath;
  localStorage.setItem(CONDUIT_RUN_PATHS_STORAGE_KEY, JSON.stringify(all));
}
