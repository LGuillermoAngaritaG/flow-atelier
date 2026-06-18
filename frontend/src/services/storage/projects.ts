import type { Project } from "@/types/project";
import { PROJECTS_KEY, ACTIVE_PROJECT_KEY } from "@/constants/kanban";

const DEFAULT_PROJECT: Project = { id: "default", name: "my project" };

export function loadProjects(): Project[] {
  try {
    const raw = localStorage.getItem(PROJECTS_KEY);
    if (!raw) return [DEFAULT_PROJECT];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [DEFAULT_PROJECT];
    return parsed;
  } catch {
    return [DEFAULT_PROJECT];
  }
}

export function saveProjects(projects: Project[]): void {
  localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects));
}

export function loadActiveProjectId(): string {
  return localStorage.getItem(ACTIVE_PROJECT_KEY) ?? "default";
}

export function saveActiveProjectId(id: string): void {
  localStorage.setItem(ACTIVE_PROJECT_KEY, id);
}
