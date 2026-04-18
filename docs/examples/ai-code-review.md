# AI code review with rollback

A Claude Code harness task reviews a diff and ends with a canonical
`VERDICT:` line. Conditional dependencies route the flow to either
`deploy` or `rollback` — exactly one branch runs.

## Scenario

You want an AI reviewer as a gate in your deploy pipeline, but you don't
want a flaky "the LLM said 'looks good'" heuristic. The conduit forces
the agent to end with one of two tokens, then uses regex-matched
conditional deps for routing.

## The conduit

```yaml title=".atelier/conduits/ai-review/conduit.yaml"
name: ai-review
description: AI code review with hard approve/reject routing
inputs:
  path: Path to review

tasks:
  - review:
      description: Claude reviews the given path
      task: |
        Review the code at {{inputs.path}} for security issues, obvious
        bugs, and missing tests. Be terse — 3-5 bullet points at most.

        Then end your response with exactly one of these two lines,
        nothing after it:
          VERDICT: APPROVE
          VERDICT: REJECT
      tool: harness:claude-code
      depends_on: []
      interactive: false

  - deploy:
      description: Deploy if approved
      task: "echo deploying... && ./bin/deploy"
      tool: tool:bash
      depends_on:
        - review.output.match(VERDICT:\s*APPROVE)

  - rollback:
      description: Rollback if rejected
      task: "echo rolling back... && ./bin/rollback"
      tool: tool:bash
      depends_on:
        - review.output.not_match(VERDICT:\s*APPROVE)
```

## Run it

```bash
atelier run ai-review --input path=src/
```

## What you should see

Claude streams its review to the terminal. Depending on the final
verdict, **one** of the following appears next:

```
✓ deploy [tool:bash]  exit=0 · 2.1s
deploying...
```

or

```
⏭ deploy  skipped (condition review.output.match(VERDICT:\s*APPROVE) not met)
✓ rollback [tool:bash]  exit=0 · 0.8s
rolling back...
```

The `⏭ skipped` panel is a yellow single-line — skipped tasks don't
trigger fail-fast and don't count as failures in the summary footer.

## Why this shape works

- The agent is forced into a **canonical output format**, not asked to
  "approve if it looks good". A regex on a canonical token is reliable;
  a regex on free-form text is not.
- `match` and `not_match` together cover every possible end state —
  whichever branch is skipped, its sibling runs.
- The `review` task is **non-interactive** — a single turn, no stdin
  prompts, so the conduit is safe to run in scripted environments.

## Variations

### Send the diff instead of a path

```yaml
- get_diff:
    task: "git diff main..HEAD"
    tool: tool:bash
    depends_on: []

- review:
    task: |
      Review this diff:

      ```
      {{get_diff.output}}
      ```

      End with VERDICT: APPROVE or VERDICT: REJECT.
    tool: harness:claude-code
    depends_on: [get_diff]
```

### Swap in Codex

Change `tool: harness:claude-code` to `tool: harness:codex`. The rest is
identical — both harnesses speak ACP with the same contract.

### Add a human override

Append a `tool:hitl` task between `review` and `deploy` to require a
human `yes` even when the AI approves. See
[Deploy pipeline with HITL gate](deploy-pipeline.md).
