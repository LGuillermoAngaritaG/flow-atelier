import type { LogEntry } from "@/types/task";
import type { CannedLine } from "@/types/log";

// Pre-authored log line pools, keyed by conduit + task name.
// The runner draws from these to feed live log streams.

type LogPool = Record<string, Record<string, CannedLine[]>>;

export const logPool: LogPool = {
  release_notes: {
    collect_commits: [
      { text: "▸ git log v0.4.2..HEAD", level: "info" },
      { text: "  47 commits found", level: "info" },
      { text: "✓ collect_commits ok", level: "ok" },
    ],
    draft_notes: [
      { text: "▸ draft_notes · claude-code", level: "info" },
      { text: "  grouping by Features / Fixes / Internal …", level: "info" },
      { text: "  6 features · 11 fixes · 3 internal", level: "info" },
      { text: "  writing opening blurb …", level: "info" },
      { text: "✓ draft_notes ok", level: "ok" },
    ],
    polish_notes: [
      { text: "▸ polish_notes · codex", level: "info" },
      { text: "  removing em-dashes", level: "info" },
      { text: "  trimming to 380 words", level: "info" },
      { text: "✓ polish_notes ok", level: "ok" },
    ],
    write_file: [
      { text: "▸ write_file CHANGELOG.md", level: "info" },
      { text: "✓ 412 bytes written", level: "ok" },
    ],
  },
  deploy_pipeline: {
    build: [
      { text: "▸ build · bun run build", level: "info" },
      { text: "  compiling 214 modules …", level: "info" },
      { text: "✓ bundle 14.2 MB", level: "ok" },
    ],
    code_review: [
      { text: "▸ code_review · claude-code", level: "info" },
      { text: "  reading diff since v0.4.2", level: "info" },
      { text: "  no schema migrations detected", level: "info" },
      { text: "  APPROVE — low-risk change", level: "acc" },
    ],
    smoke_tests: [
      { text: "▸ smoke_tests · bun test --smoke", level: "info" },
      { text: "  64 passed · 0 failed", level: "ok" },
    ],
    block_and_alert: [
      { text: "▸ block_and_alert (skipped — review approved)", level: "info" },
    ],
    deploy: [
      { text: "▸ deploy · pushing to prod", level: "info" },
      { text: "  rolling 3 of 3 replicas …", level: "info" },
      { text: "✓ deploy ok", level: "ok" },
    ],
  },
  onboard_repo: {
    clone: [
      { text: "▸ clone · git clone --depth 1", level: "info" },
      { text: "✓ 214 files", level: "ok" },
    ],
    explore: [
      { text: "▸ explore · claude-code", level: "info" },
      { text: "  walking /src …", level: "info" },
      { text: "  proposing 10 key files", level: "info" },
      { text: "  awaiting human review", level: "acc" },
    ],
    review_gate: [
      { text: "▸ review_gate · blocking on human", level: "info" },
    ],
    write_onboarding: [
      { text: "▸ write_onboarding · codex", level: "info" },
      { text: "  composing tutorial section …", level: "info" },
      { text: "  composing reference section …", level: "info" },
      { text: "✓ ONBOARDING.md written", level: "ok" },
    ],
  },
  triage_inbox: {
    fetch_issues: [
      { text: "▸ linear issues --project NEO", level: "info" },
      { text: "  42 open", level: "info" },
    ],
    classify: [
      { text: "▸ classify · claude-code", level: "info" },
      { text: "  24 bugs · 9 features · 6 questions · 3 noise", level: "info" },
    ],
    apply_labels: [
      { text: "▸ apply_labels", level: "info" },
      { text: "✓ 42 labels set", level: "ok" },
    ],
  },
  nightly_backup: {
    snapshot: [
      { text: "▸ snapshot · pg_dump", level: "info" },
      { text: "  4.2 GB", level: "ok" },
    ],
    upload: [
      { text: "▸ upload · rclone", level: "info" },
      { text: "  12.4 MB/s", level: "info" },
      { text: "✓ upload complete", level: "ok" },
    ],
    verify: [
      { text: "▸ verify · codex", level: "info" },
      { text: "  sha256 match", level: "ok" },
    ],
  },
  bench_compile: {
    checkout: [{ text: "▸ git checkout feat/simd", level: "info" }],
    run_bench: [
      { text: "▸ bench iter 1 — 412 ms", level: "info" },
      { text: "▸ bench iter 2 — 398 ms", level: "info" },
      { text: "▸ bench iter 3 — 401 ms", level: "info" },
      { text: "▸ bench iter 4 — 395 ms", level: "info" },
      { text: "▸ bench iter 5 — 397 ms", level: "ok" },
    ],
    analyze: [
      { text: "▸ analyze → bench_analysis", level: "info" },
      { text: "  median 398 ms (−4% vs main)", level: "acc" },
    ],
  },
};

// Conduits that should trigger HITL from the runner, even if they do not
// declare a tool:hitl task. Empty for now — the spec relies on the
// review_gate task in onboard_repo to trigger review.
export const hitlByConduitName = new Set<string>([]);

// ── Per-flow logs ──────────────────────────────────────────────────────────
// Built from the logPool so each prior flow has realistic log entries.

const REF = Date.parse("2026-04-15T18:00:00Z");
const MIN = 60_000;
const HR = 60 * MIN;

function canned(conduit: string, task: string, offset: number): LogEntry[] {
  const pool = logPool[conduit]?.[task] ?? [];
  return pool.map((l, i) => ({ t: offset + i * 12_000, text: l.text, level: l.level }));
}

export const flowLogs: Record<string, LogEntry[]> = {
  "a1b2c3d4-5678-4abc-9def-0012048abcde": [
    ...canned("release_notes", "collect_commits", REF - 2 * HR),
    ...canned("release_notes", "draft_notes", REF - 2 * HR + MIN),
    ...canned("release_notes", "polish_notes", REF - 2 * HR + 2 * MIN),
    ...canned("release_notes", "write_file", REF - 2 * HR + 3 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012047abcde": [
    ...canned("deploy_pipeline", "build", REF - 3 * HR - 12 * MIN),
    ...canned("deploy_pipeline", "code_review", REF - 3 * HR - 11 * MIN),
    ...canned("deploy_pipeline", "smoke_tests", REF - 3 * HR - 9 * MIN),
    ...canned("deploy_pipeline", "deploy", REF - 3 * HR - 7 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012046abcde": [
    ...canned("deploy_pipeline", "build", REF - 4 * HR),
    ...canned("deploy_pipeline", "code_review", REF - 4 * HR + MIN),
    { t: REF - 4 * HR + 3 * MIN, text: "✗ smoke_tests FAILED — 2 assertions broken", level: "err" },
  ],
  "a1b2c3d4-5678-4abc-9def-0012045abcde": [
    ...canned("triage_inbox", "fetch_issues", REF - 5 * HR - 44 * MIN),
    ...canned("triage_inbox", "classify", REF - 5 * HR - 44 * MIN + 20_000),
    ...canned("triage_inbox", "apply_labels", REF - 5 * HR - 44 * MIN + 40_000),
  ],
  "a1b2c3d4-5678-4abc-9def-0012044abcde": [
    ...canned("onboard_repo", "clone", REF - 7 * HR),
    ...canned("onboard_repo", "explore", REF - 7 * HR + MIN),
    ...canned("onboard_repo", "review_gate", REF - 7 * HR + 5 * MIN),
    ...canned("onboard_repo", "write_onboarding", REF - 7 * HR + 6 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012043abcde": [
    ...canned("nightly_backup", "snapshot", REF - 11 * HR),
    ...canned("nightly_backup", "upload", REF - 11 * HR + 2 * MIN),
    ...canned("nightly_backup", "verify", REF - 11 * HR + 5 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012042abcde": [
    ...canned("bench_compile", "checkout", REF - 13 * HR),
    ...canned("bench_compile", "run_bench", REF - 13 * HR + 30_000),
    ...canned("bench_compile", "analyze", REF - 13 * HR + 2 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012041abcde": [
    ...canned("release_notes", "collect_commits", REF - 26 * HR),
    ...canned("release_notes", "draft_notes", REF - 26 * HR + MIN),
    ...canned("release_notes", "polish_notes", REF - 26 * HR + 2 * MIN),
    ...canned("release_notes", "write_file", REF - 26 * HR + 3 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012040abcde": [
    ...canned("deploy_pipeline", "build", REF - 28 * HR),
    ...canned("deploy_pipeline", "code_review", REF - 28 * HR + MIN),
    ...canned("deploy_pipeline", "smoke_tests", REF - 28 * HR + 3 * MIN),
    ...canned("deploy_pipeline", "deploy", REF - 28 * HR + 5 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012039abcde": [
    ...canned("triage_inbox", "fetch_issues", REF - 32 * HR),
    { t: REF - 32 * HR + 20_000, text: "✗ cancelled by user", level: "err" },
  ],
  "a1b2c3d4-5678-4abc-9def-0012038abcde": [
    ...canned("nightly_backup", "snapshot", REF - 35 * HR),
    ...canned("nightly_backup", "upload", REF - 35 * HR + 2 * MIN),
    ...canned("nightly_backup", "verify", REF - 35 * HR + 5 * MIN),
  ],
  "a1b2c3d4-5678-4abc-9def-0012037abcde": [
    ...canned("onboard_repo", "clone", REF - 48 * HR),
    ...canned("onboard_repo", "explore", REF - 48 * HR + MIN),
    ...canned("onboard_repo", "review_gate", REF - 48 * HR + 5 * MIN),
    ...canned("onboard_repo", "write_onboarding", REF - 48 * HR + 8 * MIN),
  ],
};

// ── Mock API handler ───────────────────────────────────────────────────────

export function mockGetFlowLogs(flowId: string): LogEntry[] {
  return flowLogs[flowId] ?? [];
}
