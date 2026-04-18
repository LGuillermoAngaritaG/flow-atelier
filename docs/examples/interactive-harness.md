# Interactive harness session

A multi-turn Claude Code task that pairs with you on a feature. The
session stays open across turns — the executor asks **you** for the next
reply whenever the agent doesn't emit `[ATELIER_DONE]`.

## Scenario

You want Claude to help implement a new feature, but you want the
pairing session itself to be part of a conduit so the transcript is
captured, the agent picks up your `CLAUDE.md` / skills / MCP servers,
and surrounding tasks (lint, tests, commit) happen automatically after
you're done.

## The conduit

```yaml title=".atelier/conduits/pair-feature/conduit.yaml"
name: pair-feature
description: Pair with Claude on a feature, then lint and test
inputs:
  goal: What feature to build

tasks:
  - pair:
      description: Interactive pairing session with Claude
      task: |
        I want to implement: {{inputs.goal}}

        Start by proposing a short plan. Ask me clarifying questions
        before writing code. When I say we're done and you've made the
        changes, finish your response with [ATELIER_DONE].
      tool: harness:claude-code
      depends_on: []
      interactive: true

  - lint:
      description: Lint after the pairing session
      task: "uv run ruff check ."
      tool: tool:bash
      depends_on: [pair]

  - test:
      description: Run the test suite
      task: "uv run pytest -x"
      tool: tool:bash
      depends_on: [pair]
```

## Run it

```bash
atelier run pair-feature --input goal="add a /health endpoint to the FastAPI app"
```

## How the interactive loop works

1. The executor sends your task prompt as the first user message, with
   the `[ATELIER_DONE]` marker instruction appended automatically.
2. Claude streams a response. You see it live in your terminal.
3. If the response contains `[ATELIER_DONE]`, the task completes.
4. Otherwise, the executor prompts you on stdin for your next reply and
   sends it back as the next user message.
5. Any tool-permission requests from Claude show up as numbered menus
   in the middle of the exchange.
6. Loop, bounded by an internal max-turns safety net.

Once `pair` finishes, `lint` and `test` run in parallel (both only
depend on `pair`), then the flow ends.

## What you should see

A typical session:

```
> I want to implement: add a /health endpoint to the FastAPI app
> (and: [ATELIER_DONE] instruction appended silently)

[Claude proposes a 3-step plan...]
[Claude asks: "Should this be a simple 200 OK or include dependency checks?"]

atelier: next reply for Claude>
> include dependency checks — DB and redis

[Claude edits app/main.py, asks permission to run tests...]
[Allow / Deny menu appears]

> 1

[Claude runs tests, reports success, emits [ATELIER_DONE]]

✓ pair [harness:claude-code]  exit=0 · 4m 12s  (streamed live above)
✓ lint [tool:bash]  exit=0 · 0.8s
✓ test [tool:bash]  exit=0 · 3.2s
flow_id: pair-feature_9f8e7d6c_20260412T160130Z
```

Note the `(streamed live above)` tag on the `pair` panel — interactive
harness tasks are summarized compactly at the end because their
transcript already scrolled by.

## Why this is useful in a conduit

- **Transcript is captured** — `atelier logs <id> --task pair` dumps
  the full conversation for later review.
- **Surrounding tasks auto-run** — you don't have to remember to lint
  and test; they run as soon as you finish pairing.
- **Same config as standalone Claude** — the adapter reuses your
  `.claude/settings.json`, skills, subagents, MCP servers, and
  `CLAUDE.md`.

## Variations

### Cap the session length

The engine has an internal max-turns safety net, but you can also
terminate explicitly by adding "When we've made 5 exchanges, wrap up
and emit `[ATELIER_DONE]`" to the initial prompt.

### Commit after the session

```yaml
- commit_msg:
    task: "Ready to commit. What should the message say?"
    tool: tool:hitl
    depends_on: [pair, lint, test]
    inputs:
      message: "Commit message"

- commit:
    task: "git add -A && git commit -m '{{inputs.message}}'"
    tool: tool:bash
    depends_on: [commit_msg]
```

### Non-interactive variant

Set `interactive: false`. Claude runs one turn with your prompt and
returns — no stdin loop, no marker required. Use this shape when the
task is "produce this specific output" rather than "pair with me until
we're done".
