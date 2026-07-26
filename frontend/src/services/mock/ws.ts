import type { ClientWsMessage, ServerWsMessage } from "@/types/ws";
import type { Conduit, ToolType } from "@/types/conduit";
import { conduits } from "./conduits";
import { logPool } from "./logs";
import { shouldGate } from "@/runner/hitl";
import { createPrng, intBetween } from "@/runner/prng";

const rng = createPrng(0xa71e);

function baseDurationFor(tool: ToolType): number {
  switch (tool) {
    case "tool:bash":
      return intBetween(rng, 700, 1100);
    case "tool:hitl":
      return 200;
    case "tool:conduit":
      return intBetween(rng, 1000, 1400);
    default:
      // Any harness:* agent. Enumerating them here would go stale every
      // time the ACP registry gains an entry.
      return intBetween(rng, 1500, 2300);
  }
}

interface ActiveRun {
  cancelled: boolean;
  conduit: Conduit;
  pausedAtTask?: number;
  inputs?: Record<string, string>;
}

/**
 * Simulates a WebSocket server using the same mock data and timings as the
 * client-side runner engine. Drop-in replacement for the `WebSocket` class
 * — only the bits that `RunConduitSocket` actually uses are implemented.
 */
export class MockWebSocket {
  readyState = 1; // OPEN
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number; reason: string }) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;

  private timers: ReturnType<typeof setTimeout>[] = [];
  private runs = new Map<string, ActiveRun>();

  constructor(_url?: string) {
    // Fire onopen asynchronously so the real event flow is exercised
    setTimeout(() => {
      this.onopen?.({ type: "open" } as Event);
    }, 0);
  }

  send(data: string) {
    if (this.readyState !== 1) return;
    let msg: ClientWsMessage;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    switch (msg.type) {
      case "run":
        this.handleRun(msg);
        break;
      case "hitl_answer":
        this.handleHitlAnswer(msg);
        break;
      case "cancel":
        this.handleCancel(msg);
        break;
      case "resume":
        this.handleResume(msg);
        break;
    }
  }

  close() {
    this.readyState = 3; // CLOSED
    this.timers.forEach(clearTimeout);
    this.timers = [];
    this.onclose?.({ code: 1000, reason: "" } as CloseEvent);
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private emit(msg: ServerWsMessage) {
    this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
  }

  private after(delay: number, fn: () => void) {
    this.timers.push(setTimeout(fn, delay));
  }

  private handleRun(msg: {
    conduitName: string;
    inputs: Record<string, string>;
  }) {
    const conduit = conduits.find((c) => c.name === msg.conduitName);
    // Server generates the flowId — client doesn't send one
    const flowId = crypto.randomUUID();

    if (!conduit) {
      this.emit({
        type: "error",
        flowId,
        message: `conduit ${msg.conduitName} not found`,
      });
      return;
    }

    const run: ActiveRun = { cancelled: false, conduit, inputs: msg.inputs };
    this.runs.set(flowId, run);

    this.after(400, () => {
      if (run.cancelled) return;
      this.emit({ type: "started", flowId });
      this.scheduleTask(flowId, 0);
    });
  }

  private scheduleTask(flowId: string, index: number) {
    const run = this.runs.get(flowId);
    if (!run || run.cancelled) return;

    const conduitTask = run.conduit.tasks[index];
    if (!conduitTask) {
      this.emit({
        type: "flow_complete",
        flowId,
      });
      this.runs.delete(flowId);
      return;
    }

    // Conditional skip (same optimistic logic as the runner)
    if (Object.values(conduitTask.conditions ?? {}).some((c) => c.kind === "not_match")) {
      this.emit({ type: "step_status", flowId, step: conduitTask.name, status: "skipped" });
      this.scheduleTask(flowId, index + 1);
      return;
    }

    // HITL gate — pause and wait for client answer
    if (shouldGate(run.conduit, conduitTask)) {
      this.emit({ type: "step_status", flowId, step: conduitTask.name, status: "running" });
      this.emit({
        type: "hitl_request",
        flowId,
      });
      run.pausedAtTask = index;
      return;
    }

    // Ordinary task — mark running, stream logs, then mark done
    this.emit({ type: "step_status", flowId, step: conduitTask.name, status: "running" });

    const duration = baseDurationFor(conduitTask.tool);
    const pool = logPool[run.conduit.name]?.[conduitTask.name] ?? [];
    const streamWindow = Math.floor(duration * 0.8);

    if (pool.length > 0) {
      const gap = Math.max(120, Math.floor(streamWindow / pool.length));
      pool.forEach((line, i) => {
        this.after(gap * (i + 1), () => {
          const r = this.runs.get(flowId);
          if (!r || r.cancelled) return;
          this.emit({
            type: "log",
            flowId,
            entry: { t: Date.now(), text: line.text, level: line.level },
          });
        });
      });
    }

    this.after(duration, () => {
      const r = this.runs.get(flowId);
      if (!r || r.cancelled) return;
      this.emit({ type: "step_status", flowId, step: conduitTask.name, status: "done" });
      this.scheduleTask(flowId, index + 1);
    });
  }

  private handleHitlAnswer(msg: {
    flowId: string;
    answers: Record<string, string>;
  }) {
    const run = this.runs.get(msg.flowId);
    if (!run || run.cancelled || run.pausedAtTask === undefined) return;

    const taskIndex = run.pausedAtTask;
    const conduitTask = run.conduit.tasks[taskIndex];
    run.pausedAtTask = undefined;

    this.emit({
      type: "log",
      flowId: msg.flowId,
      entry: { t: Date.now(), text: "▸ resumed with answers", level: "acc" },
    });
    this.emit({
      type: "step_status",
      flowId: msg.flowId,
      step: conduitTask.name,
      status: "done",
    });
    this.scheduleTask(msg.flowId, taskIndex + 1);
  }

  private handleCancel(msg: { flowId: string }) {
    const run = this.runs.get(msg.flowId);
    if (!run) return;
    run.cancelled = true;
    this.emit({
      type: "flow_failed",
      flowId: msg.flowId,
      error: "cancelled by user",
    });
  }

  private handleResume(msg: { flowId: string }) {
    const run = this.runs.get(msg.flowId);
    if (!run) {
      this.emit({
        type: "error",
        flowId: msg.flowId,
        message: `flow ${msg.flowId} not found for resume`,
      });
      return;
    }

    // Uncancel and restart
    run.cancelled = false;
    run.pausedAtTask = undefined;

    this.after(400, () => {
      if (run.cancelled) return;
      this.emit({ type: "started", flowId: msg.flowId });
      this.scheduleTask(msg.flowId, 0);
    });
  }
}
