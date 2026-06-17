import type { Conduit, CreateConduitRequest } from "@/types/conduit";

// -------------------------------------------------------------------------
// 6 conduits, including release_notes, deploy_pipeline, onboard_repo.
// -------------------------------------------------------------------------

export const conduits: Conduit[] = [
  {
    name: "release_notes",
    description:
      "Draft release notes from a git range, run them through the editor harness, and output a markdown file.",
    runPath: "/home/runner/release-notes",
    inputs: {
      repo: "org/name",
      from: "git ref",
      to: "git ref",
    },
    tasks: [
      {
        name: "collect_commits",
        tool: "tool:bash",
        description: "git log between refs",
        task: "git log --pretty=format:'%h %s' $from..$to",
        dependsOn: [],
        position: { x: 80, y: 120 },
      },
      {
        name: "draft_notes",
        tool: "harness:claude-code",
        description: "Draft user-facing notes grouped by area",
        task: "Summarise each commit under Features / Fixes / Internal.",
        dependsOn: ["collect_commits"],
        position: { x: 320, y: 120 },
      },
      {
        name: "polish_notes",
        tool: "harness:codex",
        description: "Tighten tone, strip AI scaffolding",
        task: "Rewrite to sound human. Strip em-dashes. Keep under 400 words.",
        dependsOn: ["draft_notes"],
        position: { x: 560, y: 120 },
      },
      {
        name: "write_file",
        tool: "tool:bash",
        description: "Write CHANGELOG.md",
        task: "printf '%s' \"$polish_notes\" > CHANGELOG.md",
        dependsOn: ["polish_notes"],
        position: { x: 800, y: 120 },
      },
    ],
  },
  {
    name: "deploy_pipeline",
    description:
      "Build, run code review, gate on review result, then deploy. Demonstrates conditional match edges.",
    runPath: "/home/runner/deploy",
    inputs: {
      service: "service slug",
      ref: "git ref",
    },
    tasks: [
      {
        name: "build",
        tool: "tool:bash",
        description: "Build the service",
        task: "bun run build",
        dependsOn: [],
        position: { x: 80, y: 160 },
      },
      {
        name: "code_review",
        tool: "harness:claude-code",
        description: "Automated review of the diff since last deploy",
        task: "Review the diff. Output APPROVE or BLOCK with rationale.",
        dependsOn: ["build"],
        position: { x: 320, y: 160 },
      },
      {
        name: "smoke_tests",
        tool: "tool:bash",
        description: "Run only if code review approves",
        task: "bun test --smoke",
        dependsOn: ["code_review"],
        conditionalOn: {
          task: "code_review",
          kind: "match",
          pattern: "APPROVE",
        },
        position: { x: 560, y: 80 },
      },
      {
        name: "block_and_alert",
        tool: "tool:bash",
        description: "Only runs if review blocks",
        task: "bash scripts/alert.sh '$service blocked by review'",
        dependsOn: ["code_review"],
        conditionalOn: {
          task: "code_review",
          kind: "not_match",
          pattern: "APPROVE",
        },
        position: { x: 560, y: 260 },
      },
      {
        name: "deploy",
        tool: "tool:bash",
        description: "Push to prod",
        task: "bun run deploy $service $ref",
        dependsOn: ["smoke_tests"],
        position: { x: 800, y: 80 },
      },
    ],
  },
  {
    name: "onboard_repo",
    description:
      "Clone a repo, analyze it, and produce an onboarding doc. Requires human review before finalising.",
    runPath: "/home/runner/onboard",
    inputs: {
      url: "git url",
      audience: "who reads it",
    },
    tasks: [
      {
        name: "clone",
        tool: "tool:bash",
        description: "Shallow clone",
        task: "git clone --depth 1 $url /tmp/repo",
        dependsOn: [],
        position: { x: 80, y: 140 },
      },
      {
        name: "explore",
        tool: "harness:claude-code",
        description: "Walk the tree and identify key modules",
        task: "Read the repo. List the 10 most important files with one-line rationale.",
        dependsOn: ["clone"],
        position: { x: 320, y: 140 },
      },
      {
        name: "review_gate",
        tool: "tool:hitl",
        description: "Ask the human to confirm scope before writing",
        task: "Is the proposed outline correct for the target audience?",
        dependsOn: ["explore"],
        interactive: true,
        position: { x: 560, y: 140 },
      },
      {
        name: "write_onboarding",
        tool: "harness:codex",
        description: "Produce ONBOARDING.md",
        task: "Write ONBOARDING.md based on the confirmed outline.",
        dependsOn: ["review_gate"],
        position: { x: 800, y: 140 },
      },
    ],
  },
  {
    name: "triage_inbox",
    description:
      "Walk an issue tracker and label bugs, feature-requests, and questions. Pure bash + harness.",
    runPath: "/home/runner/triage",
    inputs: {
      project: "linear/project slug",
    },
    tasks: [
      {
        name: "fetch_issues",
        tool: "tool:bash",
        description: "Pull open issues",
        task: "linear issues --project $project --state open",
        dependsOn: [],
        position: { x: 80, y: 120 },
      },
      {
        name: "classify",
        tool: "harness:claude-code",
        description: "Classify each issue",
        task: "For each issue, return one of: bug, feature, question, noise.",
        dependsOn: ["fetch_issues"],
        position: { x: 320, y: 120 },
      },
      {
        name: "apply_labels",
        tool: "tool:bash",
        description: "Apply labels via API",
        task: "linear label apply $classified",
        dependsOn: ["classify"],
        position: { x: 560, y: 120 },
      },
    ],
  },
  {
    name: "nightly_backup",
    description:
      "Snapshot the database, push to cold storage, verify checksum. Two bashes and one harness.",
    runPath: "/home/runner/backup",
    inputs: {
      bucket: "storage bucket",
    },
    tasks: [
      {
        name: "snapshot",
        tool: "tool:bash",
        description: "pg_dump the main db",
        task: "pg_dump -Fc atelier > /tmp/snap.dump",
        dependsOn: [],
        position: { x: 80, y: 140 },
      },
      {
        name: "upload",
        tool: "tool:bash",
        description: "Push to cold storage",
        task: "rclone copy /tmp/snap.dump $bucket:",
        dependsOn: ["snapshot"],
        position: { x: 320, y: 140 },
      },
      {
        name: "verify",
        tool: "harness:codex",
        description: "Cross-check checksums and report",
        task: "Compare local and remote sha256. Flag any drift.",
        dependsOn: ["upload"],
        position: { x: 560, y: 140 },
      },
    ],
  },
  {
    name: "bench_compile",
    description:
      "Run the compiler benchmark suite on a branch, then recurse into the analysis sub-conduit.",
    runPath: "/home/runner/bench",
    inputs: {
      branch: "branch name",
      iters: "iterations",
    },
    tasks: [
      {
        name: "checkout",
        tool: "tool:bash",
        description: "Switch branches",
        task: "git checkout $branch",
        dependsOn: [],
        position: { x: 80, y: 140 },
      },
      {
        name: "run_bench",
        tool: "tool:bash",
        description: "Run the benchmark suite",
        task: "./bench/run.sh --iters $iters",
        dependsOn: ["checkout"],
        repeat: 5,
        position: { x: 320, y: 140 },
      },
      {
        name: "analyze",
        tool: "tool:conduit",
        description: "Hand off to the analysis conduit",
        task: "bench_analysis",
        dependsOn: ["run_bench"],
        position: { x: 560, y: 140 },
      },
    ],
  },
];

export function getConduit(name: string): Conduit | undefined {
  return conduits.find((c) => c.name === name);
}

// ── Mock API handlers ─────────────────────────────────────────────────────

export function mockGetConduits(): Conduit[] {
  return conduits;
}

export function mockGetConduit(name: string): Conduit | undefined {
  return getConduit(name);
}

export function mockOpenPath(
  conduitName: string,
): { opened: boolean } {
  const c = conduits.find((c) => c.name === conduitName);
  return { opened: !!c };
}

export function mockCreateConduit(req: CreateConduitRequest): Conduit {
  const existing = conduits.find((c) => c.name === req.name);
  if (existing) throw new Error(`Conduit "${req.name}" already exists`);

  const created: Conduit = {
    name: req.name,
    description: req.description,
    timeout: req.timeout,
    maxConcurrency: req.maxConcurrency,
    runPath: "",
    inputs: req.inputs ?? {},
    tasks: req.tasks,
  };
  conduits.push(created);
  return created;
}

export function mockUpdateConduit(req: CreateConduitRequest): Conduit {
  const idx = conduits.findIndex((c) => c.name === req.name);
  if (idx === -1) throw new Error(`Conduit "${req.name}" not found`);

  conduits[idx] = {
    ...conduits[idx],
    description: req.description,
    timeout: req.timeout,
    maxConcurrency: req.maxConcurrency,
    inputs: req.inputs ?? conduits[idx].inputs,
    tasks: req.tasks,
  };
  return conduits[idx];
}
