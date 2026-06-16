import { useState, useEffect } from "react";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { createTask, updateTaskData, startTask } from "@/runner/engine";
import { loadProjects } from "@/services/storage/projects";
import type { ConduitTask, ToolType } from "@/types/conduit";
import type { Task } from "@/types/task";

export type Step = "pick" | "conduit-select" | "conduit-inputs" | "task-nodes" | "node-detail" | "run-task";

interface UseNewTaskDialogParams {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editTask?: Task;
  projectId: string;
}

export function useNewTaskDialog({ open, onOpenChange, editTask, projectId }: UseNewTaskDialogParams) {
  const isEditing = !!editTask;
  const { conduits } = useConduits();

  const [step, setStep] = useState<Step>("pick");
  const [selectedConduit, setSelectedConduit] = useState(
    editTask?.name ?? conduits[0]?.name ?? "",
  );
  const conduit = getConduitSync(selectedConduit, conduits) ?? conduits[0];
  const [values, setValues] = useState<Record<string, string>>({});
  const [runPath, setRunPath] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState(projectId);
  const [runPrompt, setRunPrompt] = useState("");
  const [nodes, setNodes] = useState<ConduitTask[]>([]);
  const [, setEditNodeIdx] = useState<number | null>(null);
  const [selectedTool, setSelectedTool] = useState<ToolType>("tool:bash");
  const [nodeForm, setNodeForm] = useState({ name: "", description: "", task: "", runPath: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const projects = loadProjects();

  useEffect(() => {
    setSelectedProjectId(projectId);
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    if (isEditing && editTask) {
      setStep("run-task");
      setSelectedConduit(editTask.name);
      setValues({ ...(editTask.inputs ?? {}) });
      const c = getConduitSync(editTask.name, conduits);
      setRunPath(editTask.runPath ?? editTask.inputs?.runPath ?? c?.runPath ?? "");
      setRunPrompt(editTask.prompt ?? "");
      setSelectedProjectId(editTask.projectId);
    } else {
      setStep("pick");
      setSelectedConduit(conduits[0]?.name ?? "");
      setValues({});
      setRunPath("");
      setNodes([]);
      setEditNodeIdx(null);
      setNodeForm({ name: "", description: "", task: "", runPath: "" });
    }
  }, [open, editTask, conduits]);

  const reset = () => {
    setStep("pick");
    setSelectedConduit(conduits[0]?.name ?? "");
    setValues({});
    setRunPath("");
    setRunPrompt("");
    setNodes([]);
    setEditNodeIdx(null);
    setNodeForm({ name: "", description: "", task: "", runPath: "" });
    setFieldErrors({});
  };

  const submitConduit = () => {
    createTask({
      name: conduit.name,
      projectId: selectedProjectId,
      inputs: Object.keys(values).length > 0
        ? values
        : Object.fromEntries(
            Object.entries(conduit.inputs).map(([k, v]) => [k, typeof v === "string" ? v : (v.default ?? "")]),
          ),
      runPath: runPath || undefined,
    });
    onOpenChange(false);
    reset();
  };

  const runTask = () => {
    if (!editTask) return;
    const editConduit = getConduitSync(editTask.name, conduits);
    const isCustom = !editConduit;
    const errors: Record<string, string> = {};
    if (!runPath.trim()) errors.runPath = "Working directory is required";
    if (isCustom) {
      if (!runPrompt.trim()) errors.runPrompt = "Task / prompt is required";
    } else {
      for (const name of Object.keys(editConduit!.inputs)) {
        if (!values[name]?.trim()) errors[name] = "Required";
      }
    }
    if (Object.keys(errors).length) { setFieldErrors(errors); return; }
    setFieldErrors({});
    updateTaskData(editTask.name, {
      inputs: isCustom ? undefined : (Object.keys(values).length > 0 ? values : undefined),
      prompt: isCustom ? runPrompt || undefined : undefined,
      runPath: runPath || undefined,
    });
    startTask(editTask.name);
    onOpenChange(false);
    reset();
  };

  const openNodeForm = (tool: ToolType) => {
    setSelectedTool(tool);
    setNodeForm({ name: "", description: "", task: "", runPath: "" });
    setEditNodeIdx(null);
    setStep("node-detail");
  };

  const saveNode = () => {
    const errors: Record<string, string> = {};
    if (!nodeForm.name.trim()) errors.name = "Name is required";
    if (!nodeForm.description.trim()) errors.description = "Description is required";
    if (Object.keys(errors).length) { setFieldErrors(errors); return; }
    setFieldErrors({});
    createTask({
      name: nodeForm.name.trim(),
      description: nodeForm.description,
      prompt: nodeForm.task || undefined,
      tool: selectedTool,
      runPath: runPath || undefined,
      projectId: selectedProjectId,
      inputs: {},
    });
    onOpenChange(false);
    reset();
  };

  const editNode = (idx: number) => {
    const n = nodes[idx];
    setSelectedTool(n.tool);
    setNodeForm({ name: n.name, description: n.description, task: n.task, runPath: "" });
    setEditNodeIdx(idx);
    setStep("node-detail");
  };

  const backStep = () => {
    if (step === "conduit-inputs") setStep("conduit-select");
    else if (step === "conduit-select") setStep("pick");
    else if (step === "task-nodes") setStep("pick");
    else if (step === "node-detail") setStep("task-nodes");
  };

  const stepTitle = () => {
    if (isEditing) return editTask!.name;
    return step === "pick" ? "new task" : step === "node-detail" ? "configure task" : "new task";
  };

  const stepDesc = () => {
    if (step === "pick") return "choose type";
    if (step === "conduit-select") return "pick a conduit";
    if (step === "conduit-inputs") return `fill inputs · ${conduit.name}`;
    if (step === "task-nodes") return "add nodes to build your task";
    if (step === "node-detail") return "configure this task";
    if (step === "run-task") return "configure & run";
    return "";
  };

  const handleOpenChange = (o: boolean) => {
    onOpenChange(o);
    if (!o) reset();
  };

  const selectConduitAndAdvance = (name: string) => {
    const c = getConduitSync(name, conduits)!;
    setSelectedConduit(name);
    setValues(Object.fromEntries(Object.keys(c.inputs).map((k) => [k, ""])));
    setRunPath(c.runPath ?? "");
    setStep("conduit-inputs");
  };

  return {
    step,
    setStep,
    fieldErrors,
    conduit,
    selectedConduit,
    values,
    setValues,
    runPath,
    setRunPath,
    selectedProjectId,
    setSelectedProjectId,
    runPrompt,
    setRunPrompt,
    nodes,
    setNodes,
    nodeForm,
    setNodeForm,
    selectedTool,
    projects,
    isEditing,
    submitConduit,
    runTask,
    openNodeForm,
    saveNode,
    editNode,
    backStep,
    stepTitle,
    stepDesc,
    handleOpenChange,
    selectConduitAndAdvance,
  };
}
