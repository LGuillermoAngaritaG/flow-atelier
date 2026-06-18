import { create } from "zustand";
import { persist } from "zustand/middleware";
import { seedTasks } from "@/services/mock/tasks";
import { TASKS_KEY } from "@/constants/kanban";
import { USE_MOCK } from "@/services/client";
import type { Task, ColumnId } from "@/types/task";

const selectByColumnCache = new Map<ColumnId, Task[]>();

// Storage adapter that persists only when no task is actively running.
// Zustand v5's persist calls setItem on every state mutation — without this
// gate, every log-line tick during a mock run serializes the whole task list
// to localStorage at many writes per second.
// We use a deferred getter to avoid TDZ during store creation (the store
// variable is assigned after create() returns, but setItem runs inside it).
let _getState: (() => TaskStoreState) | null = null;
const tasksStorage = {
  getItem: (name: string) => {
    const raw = localStorage.getItem(name);
    return raw ? JSON.parse(raw) : null;
  },
  setItem: (name: string, value: unknown) => {
    const running = _getState?.()
      .tasks.some((t) => t.column === "in_progress" && t.flow) ?? false;
    if (!running) {
      localStorage.setItem(name, JSON.stringify(value));
    }
  },
  removeItem: (name: string) => localStorage.removeItem(name),
};

export interface TaskStoreState {
  tasks: Task[];
  setTasks: (next: Task[]) => void;
  updateTask: (name: string, patch: (t: Task) => Task) => void;
  upsert: (t: Task) => void;
  remove: (name: string) => void;
}

function cloneSeed(): Task[] {
  return seedTasks.map((t) => ({
    ...t,
    inputs: { ...t.inputs },
    flow: t.flow
      ? {
          ...t.flow,
          taskStatuses: { ...t.flow.taskStatuses },
          logLines: t.flow.logLines.map((l) => ({ ...l })),
          hitlRequest: t.flow.hitlRequest
            ? { ...t.flow.hitlRequest }
            : undefined,
          hitlAnswers: t.flow.hitlAnswers
            ? { ...t.flow.hitlAnswers }
            : undefined,
        }
      : undefined,
  }));
}

export const useTaskStore = create<TaskStoreState>()(
  persist(
    (set) => ({
      tasks: USE_MOCK ? cloneSeed() : [],
      setTasks: (next) => set({ tasks: next }),
      updateTask: (name, patch) =>
        set((s) => ({
          tasks: s.tasks.map((t) => (t.name === name ? patch(t) : t)),
        })),
      upsert: (t) =>
        set((s) => {
          const ix = s.tasks.findIndex((x) => x.name === t.name);
          if (ix < 0) return { tasks: [t, ...s.tasks] };
          const copy = [...s.tasks];
          copy[ix] = t;
          return { tasks: copy };
        }),
      remove: (name) =>
        set((s) => ({ tasks: s.tasks.filter((t) => t.name !== name) })),
    }),
    {
      name: TASKS_KEY,
      version: 1,
      storage: tasksStorage,
      partialize: (s) => ({
        tasks: s.tasks.filter((t) => !(t.column === "in_progress" && t.flow)),
      }),
      migrate: (persisted, version) => {
        // Clear stale mock seed data when switching to API mode
        if (!USE_MOCK && version === 0) return { tasks: [] };
        return persisted;
      },
    },
  ),
);

_getState = () => useTaskStore.getState();

export const selectRunningCount = (s: TaskStoreState) =>
  s.tasks.filter((t) => t.column === "in_progress").length;

export const selectByColumn = (col: ColumnId) => (s: TaskStoreState) => {
  const result = s.tasks.filter((t) => t.column === col);
  const cached = selectByColumnCache.get(col);
  if (cached && cached.length === result.length && cached.every((t, i) => t === result[i])) {
    return cached;
  }
  selectByColumnCache.set(col, result);
  return result;
};

export const selectByName = (name: string) => (s: TaskStoreState) =>
  s.tasks.find((t) => t.name === name);
