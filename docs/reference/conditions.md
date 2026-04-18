# Conditional dependencies

By default a `depends_on` entry is **unconditional** — the dependent
task waits for the upstream to complete successfully. You can also make
a dependency **conditional** on whether the upstream's output matches a
regex.

## Syntax

```
<task>.output.match(<regex>)        # dependency met iff regex matches
<task>.output.not_match(<regex>)    # dependency met iff regex does NOT match
```

The regex is **everything between the leftmost `(` and the last `)`** —
no quoting required, so you don't need to escape parentheses or quotes.
Python's `re.search` is used, so the pattern does not need to anchor.

## Example

```yaml
tasks:
  - review:
      description: AI review, ends with VERDICT: APPROVE or REJECT
      task: "Review /tmp/build. End with VERDICT: APPROVE or VERDICT: REJECT."
      tool: harness:claude-code
      depends_on: []

  - deploy:
      description: Deploy if review approved
      task: "make deploy"
      tool: tool:bash
      depends_on:
        - review.output.match(VERDICT:\s*APPROVE)

  - rollback:
      description: Rollback if review rejected
      task: "make rollback"
      tool: tool:bash
      depends_on:
        - review.output.not_match(VERDICT:\s*APPROVE)
```

One and only one of `deploy` / `rollback` will run, depending on how
`review` ended.

## Skip semantics

If a condition is **not met**, the dependent task is **skipped** — not
failed.

- A skip does **not** trigger fail-fast.
- Any task that references a skipped task's output — via `depends_on` or
  `{{task.output}}` — is **transitively** skipped.
- Skips show up as `⏭ skipped` in the status table and logs, with the
  reason printed alongside.

This means you can express fan-out / fan-in shapes where only one
branch completes:

```
          ┌──▶ path_a  ─┐
  review  ┤              ├─▶ downstream    (downstream sees exactly one completed parent)
          └──▶ path_b  ─┘
```

## Combining conditions

A task can list multiple conditional deps. **All** must be met for the
task to run; if any one is unmet, the task is skipped.

```yaml
depends_on:
  - tests.output.match(PASS)
  - review.output.match(VERDICT:\s*APPROVE)
```

To express "run if A matches **or** B matches", split the logic into two
separate tasks, each with one condition, and have downstream depend on
them conditionally — or produce a single upstream task whose output
carries the combined verdict.

## What conditions can't do

- No lookups inside structured data — only regex match on `output`.
- No exit-code conditions — use the output channel for signals
  (`echo FAIL` / `echo PASS`) and match on it.
- No `elif` chains — skips cascade, but you can't branch on more than
  one condition at once. Prefer a single "decision" task that emits a
  canonical verdict string.
