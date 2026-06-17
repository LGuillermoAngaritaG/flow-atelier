import { useState, useCallback, useMemo } from "react";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  DragOverlay,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { startTask } from "@/runner/engine";
import { useTaskStore } from "@/runner";
import { useConduit } from "@/hooks/useConduit";
import { getConduitCached } from "@/services/conduits";

import {
  loadProjects,
  saveProjects,
  loadActiveProjectId,
  saveActiveProjectId,
} from "@/services/storage/projects";
import { KANBAN_COLUMNS } from "@/constants/kanban";
import type { Task, ColumnId } from "@/types/task";
import { TaskCard } from "./components/TaskCard";
import { TaskCardRunning } from "./components/TaskCardRunning";
import { KanbanColumn } from "./components/KanbanColumn";
import { TaskDrawer } from "./components/TaskDrawer";
import { NewTaskDialog } from "./components/NewTaskDialog";
import { NewProjectDialog } from "./components/NewProjectDialog";
import { DeleteProjectDialog } from "./components/DeleteProjectDialog";
import { DateRangePicker } from "./components/DateRangePicker";

type DatePreset = "all" | "today" | "yesterday" | "week" | "month" | "custom";

const DATE_OPTIONS: Array<{ value: DatePreset; label: string }> = [
  { value: "all", label: "All time" },
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Date range" },
];

function dateFilterRange(preset: DatePreset, customFrom?: string, customTo?: string): [number, number] | null {
  const now = Date.now();
  const DAY = 86_400_000;
  switch (preset) {
    case "today": {
      const start = new Date(); start.setHours(0, 0, 0, 0);
      return [start.getTime(), now + DAY];
    }
    case "yesterday": {
      const start = new Date(); start.setHours(0, 0, 0, 0);
      return [start.getTime() - DAY, start.getTime()];
    }
    case "week": {
      const d = new Date(); d.setDate(d.getDate() - d.getDay());
      d.setHours(0, 0, 0, 0);
      return [d.getTime(), d.getTime() + 7 * DAY];
    }
    case "month": {
      const d = new Date(); d.setDate(1); d.setHours(0, 0, 0, 0);
      return [d.getTime(), now + DAY];
    }
    case "custom": {
      if (!customFrom || !customTo) return null;
      const [fy, fm, fd] = customFrom.split("-").map(Number);
      const [ty, tm, td] = customTo.split("-").map(Number);
      const from = new Date(fy, fm - 1, fd, 0, 0, 0, 0);
      const to = new Date(ty, tm - 1, td, 23, 59, 59, 999);
      return [from.getTime(), to.getTime()];
    }
    default:
      return null;
  }
}

const ALL_PROJECTS = "__all__";

const ALLOWED_DROPS: Partial<Record<ColumnId, ColumnId[]>> = {
  todo: ["in_progress"],
  done: ["todo", "in_progress"],
};

export function Kanban() {
  const tasks = useTaskStore((s) => s.tasks);
  const [selectedName, setSelectedName] = useState<string | undefined>();
  const [addOpen, setAddOpen] = useState(false);
  const [editTask, setEditTask] = useState<Task | undefined>();
  const [projects, setProjects] = useState(loadProjects);
  const [activeProjectId, setActiveProjectId] = useState(loadActiveProjectId);
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [customDateFrom, setCustomDateFrom] = useState("");
  const [customDateTo, setCustomDateTo] = useState("");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const setTasks = useTaskStore((s) => s.setTasks);

  const { run: conduitRun, cancel: conduitCancel, resume: conduitResume, answerHITL: conduitAnswerHITL, liveRuns } = useConduit({
    onFlowStarted: (flowId, conduitName) => {
      const task = useTaskStore.getState().tasks.find(t => t.name === conduitName && t.column === "in_progress");
      if (task) {
        useTaskStore.getState().updateTask(task.name, (t) => ({
          ...t,
          flow: { ...t.flow!, flowId },
        }));
      }
    },
    onFlowComplete: (flowId) => {
      const task = useTaskStore.getState().tasks.find(t => t.flow?.flowId === flowId);
      if (task) {
        useTaskStore.getState().updateTask(task.name, (t) => ({ ...t, column: "done" }));
      }
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor),
  );

  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const name = event.active.data.current?.taskName as string | undefined;
    if (name) {
      const t = useTaskStore.getState().tasks.find((x) => x.name === name);
      setActiveTask(t ?? null);
    }
  }, []);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    setActiveTask(null);
    const { active, over } = event;
    if (!over) return;

    const sourceColumn = active.data.current?.column as ColumnId;
    const targetColumn = over.id as ColumnId;
    const taskName = active.data.current?.taskName as string;

    const allowed = ALLOWED_DROPS[sourceColumn];
    if (!allowed?.includes(targetColumn)) return;

    if (targetColumn === "in_progress") {
      const result = startTask(taskName);
      if (result?.needsConduitRun) {
        const task = useTaskStore.getState().tasks.find(t => t.name === taskName);
        const conduit = task ? getConduitCached(task.name) : undefined;
        if (conduit && task) {
          conduitRun(conduit.name, task.inputs, task.runPath ?? "");
        }
      }
    } else {
      useTaskStore.getState().updateTask(taskName, (t) => ({
        ...t,
        column: targetColumn,
        flow: undefined,
      }));
    }
  }, []);

  const handleDragCancel = useCallback(() => setActiveTask(null), []);

  const showAllProjects = activeProjectId === ALL_PROJECTS;
  const activeProject = projects.find((p) => p.id === activeProjectId) ?? projects[0] ?? { id: "", name: "" };

  const handleProjectSwitch = useCallback((id: string) => {
    if (id === "__new__") {
      setNewProjectOpen(true);
      return;
    }
    setActiveProjectId(id);
    saveActiveProjectId(id);
  }, []);

  const handleCreateProject = useCallback((name: string) => {
    const newProject = { id: `proj-${Date.now()}`, name };
    const updated = [...projects, newProject];
    setProjects(updated);
    saveProjects(updated);
    setActiveProjectId(newProject.id);
    saveActiveProjectId(newProject.id);
  }, [projects]);

  const projectHasRunningTasks = tasks.some(
    (t) => t.projectId === activeProject.id && t.column === "in_progress",
  );

  const projectHasHistory = tasks.some(
    (t) => t.projectId === activeProject.id && t.flow,
  );

  const handleDeleteProject = useCallback(() => {
    const remaining = projects.filter((p) => p.id !== activeProject.id);
    setProjects(remaining);
    saveProjects(remaining);
    setTasks(tasks.filter((t) => t.projectId !== activeProject.id));
    const nextActive = remaining[0];
    if (nextActive) {
      setActiveProjectId(nextActive.id);
      saveActiveProjectId(nextActive.id);
    } else {
      setActiveProjectId(ALL_PROJECTS);
      saveActiveProjectId(ALL_PROJECTS);
    }
  }, [projects, activeProject.id, tasks, setTasks]);

  const filterRange = useMemo(() => dateFilterRange(datePreset, customDateFrom, customDateTo), [datePreset, customDateFrom, customDateTo]);

  const filterByDate = useCallback(
    (colId: ColumnId, colTasks: Task[]) => {
      if (colId === "todo" || !filterRange) return colTasks;
      const [from, to] = filterRange;
      return colTasks.filter((t) => {
        const ts = t.flow?.startedAt ?? t.createdAt;
        return ts >= from && ts <= to;
      });
    },
    [filterRange],
  );

  const handleTaskClick = useCallback((task: Task) => {
    if (task.column === "todo") {
      setEditTask(task);
      setAddOpen(true);
    } else {
      setSelectedName(task.name);
    }
  }, []);

  const closeDialog = useCallback((open: boolean) => {
    setAddOpen(open);
    if (!open) setEditTask(undefined);
  }, []);

  const projectFilter = useCallback((t: Task) => {
    if (t.projectId === "__dashboard__") return false;
    if (showAllProjects) return true;
    return t.projectId === activeProject.id;
  }, [showAllProjects, activeProject.id]);

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-6 lg:px-10 lg:py-10">
      <header className="mb-6 lg:mb-10 flex items-baseline justify-between gap-4 lg:gap-10 border-b border-border pb-4 lg:pb-7">
        <h1 className="page-title">
          Run a <em className="text-primary not-italic italic">task</em>
        </h1>
      </header>

      <div className="mx-auto max-w-[1280px]">
        {/* Toolbar: project + date dropdowns */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            value={activeProjectId}
            onChange={(e) => handleProjectSwitch(e.target.value)}
            className="h-7 cursor-pointer rounded border border-border bg-background px-2 font-mono text-[12px] text-foreground outline-none focus:border-primary"
          >
            <option value={ALL_PROJECTS}>all projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
            <option value="__new__">+ new project</option>
          </select>

          <select
            value={datePreset}
            onChange={(e) => setDatePreset(e.target.value as DatePreset)}
            className="h-7 cursor-pointer rounded border border-border bg-background px-2 font-mono text-[12px] text-foreground outline-none focus:border-primary"
          >
            {DATE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {datePreset === "custom" && (
            <DateRangePicker
              from={customDateFrom}
              to={customDateTo}
              onConfirm={(f, t) => {
                setCustomDateFrom(f);
                setCustomDateTo(t);
              }}
            />
          )}

          <div className="ml-auto">
            {!showAllProjects && (
              <button
                type="button"
                disabled={projectHasRunningTasks}
                onClick={() => setDeleteProjectOpen(true)}
                className="h-7 cursor-pointer rounded border border-border bg-background px-3 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:border-destructive hover:text-destructive disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted-foreground"
              >
                delete project
              </button>
            )}
          </div>
        </div>

        <DndContext
          sensors={sensors}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
          {KANBAN_COLUMNS.map((col) => {
            let colTasks = tasks
              .filter((t) => t.column === col.id && projectFilter(t))
              .sort((a, b) => b.createdAt - a.createdAt);
            colTasks = filterByDate(col.id, colTasks);

            return (
              <KanbanColumn
                key={col.id}
                id={col.id}
                title={col.title}
                count={colTasks.length}
                onAdd={col.id === "todo" ? () => { setEditTask(undefined); setAddOpen(true); } : undefined}
              >
                {colTasks.map((t) => (
                  <CardSelector
                    key={t.name}
                    task={t}
                    selected={selectedName === t.name}
                    onClick={() => handleTaskClick(t)}
                  />
                ))}
                {colTasks.length === 0 && (
                  <div className="font-mono text-[11px] text-muted-foreground/60">
                    — empty —
                  </div>
                )}
              </KanbanColumn>
            );
          })}
        </div>
        <DragOverlay dropAnimation={null}>
          {activeTask && (
            <div className="h-[80px] border border-primary/60 bg-card px-3 py-2.5 shadow-lg">
              <div className="min-w-0 font-mono text-[14px] leading-snug text-foreground line-clamp-1">
                {activeTask.name}
              </div>
              {activeTask.description && (
                <div className="mt-1 text-[12px] leading-snug text-muted-foreground line-clamp-1">
                  {activeTask.description}
                </div>
              )}
            </div>
          )}
        </DragOverlay>
        </DndContext>
      </div>

      <TaskDrawer
        taskName={selectedName}
        onClose={() => setSelectedName(undefined)}
        liveRuns={liveRuns}
        onCancelRun={conduitCancel}
        onResumeRun={conduitResume}
        onRespondToHitl={conduitAnswerHITL}
      />
      <NewTaskDialog open={addOpen} onOpenChange={closeDialog} editTask={editTask} projectId={showAllProjects ? (projects[0]?.id ?? "default") : activeProject.id} />
      <NewProjectDialog open={newProjectOpen} onOpenChange={setNewProjectOpen} onCreate={handleCreateProject} />
      <DeleteProjectDialog
        open={deleteProjectOpen}
        onOpenChange={setDeleteProjectOpen}
        projectName={activeProject?.name ?? ""}
        hasHistory={projectHasHistory}
        onConfirm={handleDeleteProject}
      />
    </div>
  );
}

function CardSelector({
  task,
  selected,
  onClick,
}: {
  task: Task;
  selected: boolean;
  onClick: () => void;
}) {
  if (task.column === "in_progress" && task.flow) {
    return <TaskCardRunning task={task} selected={selected} onClick={onClick} />;
  }
  return <TaskCard task={task} selected={selected} onClick={onClick} />;
}
