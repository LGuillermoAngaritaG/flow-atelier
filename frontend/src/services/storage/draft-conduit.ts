import { DRAFT_CONDUIT_STORAGE_KEY } from "@/constants/dashboard";
import type { Conduit } from "@/types/conduit";

export function loadDraftConduit(): Conduit | null {
  try {
    const raw = localStorage.getItem(DRAFT_CONDUIT_STORAGE_KEY);
    if (!raw) return null;
    const parsed: Conduit = JSON.parse(raw);
    if (Array.isArray(parsed.inputs)) {
      localStorage.removeItem(DRAFT_CONDUIT_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveDraftConduit(conduit: Conduit): void {
  localStorage.setItem(DRAFT_CONDUIT_STORAGE_KEY, JSON.stringify(conduit));
}

export function clearDraftConduit(): void {
  localStorage.removeItem(DRAFT_CONDUIT_STORAGE_KEY);
}
