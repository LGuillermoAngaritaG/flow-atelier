import { useReducer, useRef, useCallback } from "react";
import { RunConduitSocket } from "@/services/api/run-conduit";
import type {
  ServerWsMessage,
  BackendLogEntry,
  BackendTask,
  WsHitlRequestInput,
} from "@/types/ws";
import type { HitlInput, HitlRequest, LogEntry, FlowTaskStatus } from "@/types/task";

// ── Types ──────────────────────────────────────────────────────────────────

export type LiveRunStatus = "running" | "done" | "cancelled" | "failed";

export interface LiveRun {
  flowId: string;
  conduitName: string;
  startedAt: number;
  status: LiveRunStatus;
  logLines: LogEntry[];
  taskStatuses: Record<string, FlowTaskStatus>;
  hitlRequest?: HitlRequest;
  hitlAnswers?: Record<string, string>;
  runPath: string;
  inputs: Record<string, string>;
  parentFlowId?: string;
  parentTask?: string;
}

interface UseConduitOptions {
  onFlowStarted?: (flowId: string, conduitName: string) => void;
  onFlowComplete?: (flowId: string) => void;
}

// ── Translation helpers ───────────────────────────────────────────────────

export function isMockEntry(entry: BackendLogEntry | LogEntry): entry is LogEntry {
  return "text" in entry && "level" in entry;
}

export function backendLogToLines(entry: BackendLogEntry): LogEntry[] {
  const level: LogEntry["level"] = entry.exitCode === 0 ? "ok" : "err";
  const t = Date.parse(entry.startedAt) || Date.now();
  const task = entry.task || undefined;
  const lines: LogEntry[] = [];

  if (entry.command) {
    lines.push({ t, text: `$ ${entry.command}`, level: "info", task });
  }

  for (const raw of entry.stdout.split("\n")) {
    const text = raw.trim();
    if (text) lines.push({ t, text, level, task });
  }

  for (const raw of entry.stderr.split("\n")) {
    const text = raw.trim();
    if (text) lines.push({ t, text, level: "err", task });
  }

  if (entry.output && entry.output !== entry.stdout) {
    lines.push({ t, text: entry.output, level, task });
  }

  return lines;
}

export function taskToLine(detail: BackendTask, task?: string): LogEntry | null {
  const t = Date.parse(detail.timestamp) || Date.now();
  switch (detail.kind) {
    case "thinking":
      return detail.text ? { t, text: detail.text, level: "info", task } : null;
    case "tool_call":
      return { t, text: `→ ${detail.toolName}`, level: "acc", task };
    case "tool_result": {
      const text = detail.toolOutput || detail.toolStatus;
      const level = detail.toolStatus === "error" ? "err" : "ok";
      return text ? { t, text, level, task } : null;
    }
    default:
      return null;
  }
}

export function mapStepStatus(raw: string): FlowTaskStatus {
  if (raw === "completed") return "done";
  if (raw === "cancelled") return "failed";
  return raw as FlowTaskStatus;
}

// ── Reducer ───────────────────────────────────────────────────────────────

export type Action =
  | { type: "WS_STARTED"; flowId: string; conduitName: string; runPath: string; inputs: Record<string, string>; parentFlowId?: string; parentTask?: string }
  | { type: "WS_STEP"; flowId: string; line: LogEntry }
  | { type: "WS_LOG"; flowId: string; lines: LogEntry[] }
  | { type: "WS_STEP_STATUS"; flowId: string; step: string; status: FlowTaskStatus; marker?: LogEntry }
  | { type: "WS_HITL_REQUEST"; flowId: string; inputs: WsHitlRequestInput[] | undefined; taskName?: string }
  | { type: "WS_FLOW_COMPLETE"; flowId: string }
  | { type: "WS_FLOW_FAILED"; flowId: string; error: string }
  | { type: "CANCEL"; flowId: string }
  | { type: "RESUME"; flowId: string; conduitName?: string }
  | { type: "ANSWER_HITL"; flowId: string; answers: Record<string, string> };

export interface State {
  runs: Map<string, LiveRun>;
}

function updateRun(next: Map<string, LiveRun>, flowId: string, patch: Partial<LiveRun>) {
  const run = next.get(flowId);
  if (run) next.set(flowId, { ...run, ...patch });
}

export function reducer(state: State, action: Action): State {
  const next = new Map(state.runs);

  switch (action.type) {
    case "WS_STARTED": {
      const existing = next.get(action.flowId);
      if (existing) {
        // Resume case — run already exists, just add the log line
        next.set(action.flowId, {
          ...existing,
          logLines: [...existing.logLines, { t: Date.now(), text: "▸ flow resumed", level: "info" }],
        });
      } else if (action.parentFlowId) {
        // Child flow started by a sub-conduit task
        next.set(action.flowId, {
          flowId: action.flowId,
          conduitName: action.conduitName,
          startedAt: Date.now(),
          status: "running",
          logLines: [{ t: Date.now(), text: "▸ flow started", level: "info" }],
          taskStatuses: {},
          runPath: "",
          inputs: {},
          parentFlowId: action.parentFlowId,
          parentTask: action.parentTask,
        });
        // Add a marker to the parent's logs
        const parent = next.get(action.parentFlowId);
        if (parent) {
          next.set(action.parentFlowId, {
            ...parent,
            logLines: [...parent.logLines, {
              t: Date.now(),
              text: `▸ sub-conduit started: ${action.conduitName}`,
              level: "info" as const,
              task: action.parentTask,
            }],
          });
        }
      } else {
        // Fresh top-level run — create from pending metadata
        next.set(action.flowId, {
          flowId: action.flowId,
          conduitName: action.conduitName,
          startedAt: Date.now(),
          status: "running",
          logLines: [{ t: Date.now(), text: "▸ flow started", level: "info" }],
          taskStatuses: {},
          runPath: action.runPath,
          inputs: action.inputs,
        });
      }
      return { runs: next };
    }

    case "WS_STEP": {
      const run = next.get(action.flowId);
      if (run) next.set(action.flowId, { ...run, logLines: [...run.logLines, action.line] });
      return { runs: next };
    }

    case "WS_LOG": {
      const run = next.get(action.flowId);
      if (run) next.set(action.flowId, { ...run, logLines: [...run.logLines, ...action.lines] });
      return { runs: next };
    }

    case "WS_STEP_STATUS": {
      const run = next.get(action.flowId);
      if (run) {
        const logs = action.marker ? [...run.logLines, action.marker] : run.logLines;
        next.set(action.flowId, {
          ...run,
          logLines: logs,
          taskStatuses: { ...run.taskStatuses, [action.step]: action.status },
        });
      }
      return { runs: next };
    }

    case "WS_HITL_REQUEST": {
      const run = next.get(action.flowId);
      if (run) {
        const lastLog = run.logLines[run.logLines.length - 1];
        const hitlInputs: HitlInput[] = (action.inputs ?? []).map((i) => ({
          name: i.name,
          description: i.description,
        }));
        next.set(action.flowId, {
          ...run,
          hitlRequest: {
            fromTool: "tool:hitl" as const,
            comment: lastLog?.text ?? "",
            taskName: action.taskName,
            inputs: hitlInputs.length ? hitlInputs : undefined,
          },
        });
      }
      return { runs: next };
    }

    case "WS_FLOW_COMPLETE": {
      updateRun(next, action.flowId, {
        status: "done",
        logLines: [...(next.get(action.flowId)?.logLines ?? []), { t: Date.now(), text: "✓ flow complete", level: "ok" }],
      });
      return { runs: next };
    }

    case "WS_FLOW_FAILED": {
      const run = next.get(action.flowId);
      if (run) {
        // Don't overwrite a user-initiated cancel
        const status = run.status === "cancelled" ? "cancelled" : "failed";
        next.set(action.flowId, {
          ...run,
          status,
          logLines: [...run.logLines, { t: Date.now(), text: `✗ ${action.error}`, level: "err" }],
        });
      }
      return { runs: next };
    }

    case "CANCEL": {
      const run = next.get(action.flowId);
      if (run && run.status === "running") {
        next.set(action.flowId, { ...run, status: "cancelled" });
      }
      return { runs: next };
    }

    case "RESUME": {
      const run = next.get(action.flowId);
      if (run) {
        // Preserve prior logs/statuses — WS_STARTED will append a "flow resumed" marker
        next.set(action.flowId, {
          ...run,
          status: "running",
          hitlRequest: undefined,
          hitlAnswers: undefined,
        });
      } else {
        // Prior flow from API — create a LiveRun with conduit name from action
        next.set(action.flowId, {
          flowId: action.flowId,
          conduitName: action.conduitName ?? "",
          startedAt: Date.now(),
          status: "running",
          logLines: [],
          taskStatuses: {},
          runPath: "",
          inputs: {},
        });
      }
      return { runs: next };
    }

    case "ANSWER_HITL": {
      const run = next.get(action.flowId);
      if (run) {
        next.set(action.flowId, { ...run, hitlAnswers: action.answers, hitlRequest: undefined });
      }
      return { runs: next };
    }

    default:
      return state;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────

// Track what we've sent so we can route the `started` response
// back to the right conduitName. FIFO — messages arrive in order.
interface PendingRun {
  conduitName: string;
  runPath: string;
  inputs: Record<string, string>;
}

export function useConduit(opts: UseConduitOptions = {}) {
  const [state, dispatch] = useReducer(reducer, { runs: new Map() });
  const socketRef = useRef<RunConduitSocket | null>(null);
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;

  const onFlowStartedRef = useRef(opts.onFlowStarted);
  onFlowStartedRef.current = opts.onFlowStarted;

  const onFlowCompleteRef = useRef(opts.onFlowComplete);
  onFlowCompleteRef.current = opts.onFlowComplete;

  const pendingRef = useRef<PendingRun[]>([]);

  const liveRuns = Array.from(state.runs.values());

  const handleWsMessage = useCallback((msg: ServerWsMessage) => {
    const d = dispatchRef.current;

    switch (msg.type) {
      case "started": {
        if (msg.parentFlowId) {
          // Child flow started by a sub-conduit — no pending run to match
          d({
            type: "WS_STARTED",
            flowId: msg.flowId,
            conduitName: msg.conduitName ?? "",
            runPath: "",
            inputs: {},
            parentFlowId: msg.parentFlowId,
            parentTask: msg.parentTask,
          });
        } else {
          // Top-level run — match to the pending run we sent earliest
          const pending = pendingRef.current.shift();
          const name = pending?.conduitName ?? "";
          d({
            type: "WS_STARTED",
            flowId: msg.flowId,
            conduitName: name,
            runPath: pending?.runPath ?? "",
            inputs: pending?.inputs ?? {},
          });
          onFlowStartedRef.current?.(msg.flowId, name);
        }
        break;
      }
      case "step": {
        const line = taskToLine(msg.step, msg.task);
        if (line) d({ type: "WS_STEP", flowId: msg.flowId, line });
        break;
      }
      case "log": {
        const lines = isMockEntry(msg.entry)
          ? [msg.entry]
          : backendLogToLines(msg.entry);
        if (lines.length) d({ type: "WS_LOG", flowId: msg.flowId, lines });
        break;
      }
      case "step_status": {
        const status = mapStepStatus(msg.status);
        let marker: LogEntry | undefined;
        if (status === "running") {
          marker = { t: Date.now(), text: `▸ ${msg.step}`, level: "info", task: msg.step };
        } else if (status === "done") {
          marker = { t: Date.now(), text: `✓ ${msg.step}`, level: "ok", task: msg.step };
        } else if (status === "failed") {
          marker = { t: Date.now(), text: `✗ ${msg.step}`, level: "err", task: msg.step };
        }
        d({ type: "WS_STEP_STATUS", flowId: msg.flowId, step: msg.step, status, marker });
        break;
      }
      case "hitl_request":
        d({ type: "WS_HITL_REQUEST", flowId: msg.flowId, inputs: msg.inputs, taskName: msg.task });
        break;
      case "flow_complete":
        d({ type: "WS_FLOW_COMPLETE", flowId: msg.flowId });
        onFlowCompleteRef.current?.(msg.flowId);
        break;
      case "flow_failed":
        d({ type: "WS_FLOW_FAILED", flowId: msg.flowId, error: msg.error });
        onFlowCompleteRef.current?.(msg.flowId);
        break;
      case "error":
        console.error("[ws] server error:", msg.message);
        if (msg.flowId) {
          d({ type: "WS_LOG", flowId: msg.flowId, lines: [{ t: Date.now(), text: `✗ ${msg.message}`, level: "err" as const }] });
        }
        break;
    }
  }, []);

  const getOrCreateSocket = useCallback(() => {
    const existing = socketRef.current;
    if (existing && existing.readyState <= WebSocket.OPEN) return existing;

    const sock = new RunConduitSocket();
    sock.onMessage = handleWsMessage;
    sock.onClose = () => {
      if (socketRef.current === sock) socketRef.current = null;
    };
    socketRef.current = sock;
    return sock;
  }, [handleWsMessage]);

  const run = useCallback(
    (conduitName: string, inputs: Record<string, string>, runPath: string) => {
      // Stash metadata so we can build the LiveRun when `started` arrives
      pendingRef.current.push({ conduitName, runPath, inputs });

      const sock = getOrCreateSocket();
      sock.waitForOpen().then(() => {
        sock.send({ type: "run", conduitName, inputs, runPath });
      });
    },
    [getOrCreateSocket],
  );

  const cancel = useCallback(
    (flowId: string) => {
      dispatch({ type: "CANCEL", flowId });
      const sock = socketRef.current;
      if (sock) sock.send({ type: "cancel", flowId });
    },
    [],
  );

  const resume = useCallback(
    (flowId: string, conduitName?: string) => {
      dispatch({ type: "RESUME", flowId, conduitName });
      const sock = getOrCreateSocket();
      sock.waitForOpen().then(() => {
        sock.send({ type: "resume", flowId });
      });
    },
    [getOrCreateSocket],
  );

  const answerHITL = useCallback(
    (flowId: string, answers: Record<string, string>) => {
      dispatch({ type: "ANSWER_HITL", flowId, answers });
      const sock = socketRef.current;
      if (sock) sock.send({ type: "hitl_answer", flowId, answers });
    },
    [],
  );

  return { run, cancel, resume, answerHITL, liveRuns } as const;
}
