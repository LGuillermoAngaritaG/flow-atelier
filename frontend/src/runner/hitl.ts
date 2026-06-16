import type { Conduit, ConduitTask } from "@/types/conduit";
import { hitlByConduitName } from "@/services/mock/logs";
import type { HitlRequest } from "@/types/task";

export function shouldGate(conduit: Conduit, task: ConduitTask): boolean {
  if (task.tool === "tool:hitl") return true;
  return hitlByConduitName.has(conduit.name);
}

export function buildHitlRequest(
  _conduit: Conduit,
  task: ConduitTask,
): HitlRequest {
  return { fromTool: task.tool, comment: "" };
}
