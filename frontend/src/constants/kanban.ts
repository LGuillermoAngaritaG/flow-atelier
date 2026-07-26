import type { ColumnId } from "@/types/task";

export const KANBAN_COLUMNS: Array<{ id: ColumnId; title: string }> = [
  { id: "todo", title: "todo" },
  { id: "in_progress", title: "in progress" },
  { id: "done", title: "done" },
];

export const STATUS_BORDER: Record<string, string> = {
  idle: "border-border/60",
  needs_human: "border-warning",
  complete: "border-ok",
};

export const KANBAN_SCROLL_THRESHOLD = 5;

export const PROJECTS_KEY = "atelier-projects";
export const ACTIVE_PROJECT_KEY = "atelier-active-project";
export const TASKS_KEY = "atelier-tasks";
