export type ToolType =
  | "tool:bash"
  | "tool:hitl"
  | "tool:conduit"
  | "harness:claude-code"
  | "harness:codex"
  | "harness:copilot"
  | "harness:cursor";

export interface ConduitTask {
  name: string;
  tool: ToolType;
  description: string;
  task: string;
  dependsOn: string[];
  conditionalOn?: {
    task: string;
    kind: "match" | "not_match";
    pattern: string;
  };
  interactive?: boolean;
  repeat?: number;
  inputs?: Record<string, string>;
  position?: { x: number; y: number };
}

export interface CreateConduitRequest {
  name: string;
  description: string;
  inputs: Record<string, string | InputSpec>;
  timeout?: number;
  maxConcurrency?: number;
  tasks: ConduitTask[];
}

export interface InputSpec {
  description: string;
  default?: string | null;
}

/** Extract a display string from a conduit input hint (string or InputSpec). */
export function hintStr(hint: string | InputSpec): string {
  return typeof hint === "string" ? hint : hint.description;
}

/** Slugify a task name: replace non-alphanumeric chars with underscores. */
export function slugifyTaskName(name: string): string {
  return name.replace(/[^A-Za-z0-9_]+/g, "_");
}

export interface Conduit {
  name: string;
  description: string;
  timeout?: number;
  maxConcurrency?: number;
  runPath?: string;
  inputs: Record<string, string | InputSpec>;
  tasks: ConduitTask[];
}
