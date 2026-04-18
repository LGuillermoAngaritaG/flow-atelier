# Deploy pipeline with HITL gate

A realistic CI/CD shape: clone, test (with retries), AI review, human
approval, deploy — with automatic rollback if the AI rejects.

## Scenario

You want the AI reviewer to act as a **filter** (approve or reject), and
you want a **human** as the final gate before production. If the AI
rejects, skip the human gate entirely and go straight to rollback.

## The conduit

```yaml title=".atelier/conduits/deploy-pipeline/conduit.yaml"
name: deploy-pipeline
description: Clone → test → AI review → human gate → deploy (or rollback)
timeout: 3600
max_concurrency: 3

inputs:
  repo_url: The git repo URL
  branch: Branch to deploy
  env: Target environment (staging | prod)

tasks:
  - clone_repo:
      description: Clone the repo at the given branch
      task: "git clone -b {{inputs.branch}} {{inputs.repo_url}} /tmp/build"
      tool: tool:bash
      depends_on: []

  - run_tests:
      description: Run tests up to 3 times (flaky-test tolerant)
      task: "cd /tmp/build && make test"
      tool: tool:bash
      depends_on: [clone_repo]
      repeat: 3

  - code_review:
      description: AI security + correctness review
      task: |
        Review /tmp/build/src for security issues and correctness bugs.
        Be terse. End with exactly one of:
          VERDICT: APPROVE
          VERDICT: REJECT
      tool: harness:claude-code
      depends_on: [clone_repo]
      interactive: false

  - approve:
      description: Human gate (only reached if AI approved)
      task: "Final confirmation before deploying to {{inputs.env}}."
      tool: tool:hitl
      depends_on:
        - run_tests
        - code_review.output.match(VERDICT:\s*APPROVE)
      inputs:
        confirm: "Type 'yes' to approve deploy"
        reason: "Short reason for the decision"

  - deploy:
      description: Run the deploy sub-conduit
      task: deploy_to_env
      tool: tool:conduit
      depends_on:
        - approve.output.match(confirm:\s*yes)
      inputs:
        target_env: "{{inputs.env}}"
        build_path: /tmp/build

  - rollback:
      description: Rollback if the AI review rejected
      task: "cd /tmp/build && make rollback"
      tool: tool:bash
      depends_on:
        - code_review.output.not_match(VERDICT:\s*APPROVE)
```

## Run it

```bash
atelier run deploy-pipeline \
  --input repo_url=https://github.com/acme/app.git \
  --input branch=release/v2.3 \
  --input env=staging
```

## What you should see

A typical "approved" path:

1. **`clone_repo`** — green panel, exit 0.
2. **`run_tests (1/3)` … `(3/3)`** — three sequential green panels.
3. **`code_review`** — Claude's review streams live; the final line is
   `VERDICT: APPROVE`.
4. **`approve`** — the executor prints the prompt and asks you for
   `confirm` and `reason` on stdin.
5. **`deploy`** — a nested flow id appears, and the child conduit's
   tasks render beneath.
6. **`rollback`** — yellow `⏭ skipped` (the `not_match` didn't match).

On "rejected":

1. `clone_repo`, `run_tests`, `code_review` all run.
2. `approve` is **skipped** (the `match(APPROVE)` condition failed).
3. `deploy` is **transitively skipped** (it depends on `approve`).
4. `rollback` runs — green panel.

## Why this shape works

- `run_tests` with `repeat: 3` re-runs sequentially on flake, but the
  engine short-circuits on the first success — you don't pay for the
  extra iterations when the first passes.
- The human gate sits **after** the AI filter, so you're only prompted
  when there's a real decision to make. AI-rejected runs never wake
  the human.
- The rollback branch depends on `not_match(APPROVE)`, so it runs
  exactly when the human gate would have been skipped.

## Variations

### Add a slack notification on deploy

```yaml
- notify:
    description: Post to slack after deploy
    task: "curl -X POST -d 'deployed {{inputs.env}}' $SLACK_WEBHOOK"
    tool: tool:bash
    depends_on: [deploy]
```

### Parallel test + lint before review

Add a sibling `run_lint` task with `depends_on: [clone_repo]` — it'll
run in parallel with `run_tests` up to the `max_concurrency` cap.

### Require the human to also reject on AI failure

Currently `rollback` is fully automatic when the AI rejects. To put a
human in the rollback path too, change its `depends_on` to gate on a
second HITL task.
