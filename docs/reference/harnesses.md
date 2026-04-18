# Harness tasks

Harness tasks run an AI coding agent as part of your conduit. Two tools
are built in:

- `harness:claude-code` — [Claude Code](https://claude.com/claude-code)
- `harness:codex` — [OpenAI Codex](https://github.com/openai/codex)

Both speak the **[Agent Client Protocol](https://agentclientprotocol.com)**
(ACP) over stdio, via the official Zed adapters. This means the agent
can:

- Request **permission** before running a tool (shown as a numbered
  menu on your terminal).
- Ask the user a **free-form question** mid-turn.
- Hold a **multi-turn conversation** with the flow when
  `interactive: true`.

Both harnesses reuse your existing local CLI configuration —
project-level `.claude/settings.json`, skills, subagents, hooks, MCP
servers, `CLAUDE.md` (for Claude) and `~/.codex/config.toml`, auth,
`AGENTS.md` (for Codex).

## Non-interactive (single turn)

```yaml
- review:
    description: AI review
    task: |
      Review /tmp/build/src for security issues.
      End your response with exactly one of:
      VERDICT: APPROVE
      VERDICT: REJECT
    tool: harness:claude-code
    depends_on: [clone_repo]
    interactive: false
```

The agent runs a single turn and returns whatever it streamed before
`stop_reason`. That transcript is the task's `output`, so downstream
tasks can match on it:

```yaml
depends_on:
  - review.output.match(VERDICT:\s*APPROVE)
```

## Interactive (multi-turn)

When `interactive: true`, flow-atelier appends the following instruction
to every user message it sends to the agent:

> When — and only when — you are completely finished, output the exact
> token `[ATELIER_DONE]` to signal completion.

The executor keeps the ACP session open across turns:

1. Sends the (resolved + suffixed) task prompt as a `session/prompt`.
2. Streams the agent's response chunks to your terminal as they arrive.
3. If the chunk buffer now contains `[ATELIER_DONE]`, the task completes.
4. Otherwise it asks you for your next reply on the terminal and sends
   that back as the next user message (marker suffix re-appended).
5. Loop, bounded by an internal max-turns safety net.

```yaml
- pair_with_claude:
    description: Pair-program on a new feature
    task: "Let's implement the new /health endpoint. Start by proposing a plan."
    tool: harness:claude-code
    interactive: true
```

!!! tip "Live streaming"
    Interactive harness tasks stream to your terminal live, so at the
    end of the task `atelier run` prints a compact one-line summary
    rather than a duplicate panel — you already saw the output.

## Permission requests

When the agent asks to run a tool (e.g. "run `rm -rf build/`?"), the
executor surfaces a numbered menu on your terminal:

```
[1] Allow once
[2] Allow and don't ask again this session
[3] Deny
Your choice:
```

Your choice is returned to the agent as the permission outcome. This
works identically in both interactive and non-interactive mode.

## Pinning adapter versions

By default `atelier` launches the adapters via `npx`, which fetches the
latest published version. To pin or point at a locally installed
adapter, set environment variables:

```bash
# JSON array of argv
export ATELIER_CLAUDE_LAUNCH_CMD='["npx","@zed-industries/claude-code-acp@0.5.2"]'
export ATELIER_CODEX_LAUNCH_CMD='["npx","@zed-industries/codex-acp@0.4.1"]'
```

See `.env.example` in the repo for the full list of overrides.

## Harness caveats

- First-run `npx` fetch can take ~10s and needs network.
- Agents use your local auth — make sure `claude` / `codex` work
  standalone before invoking them from a conduit.
- Long interactive sessions are bounded by an internal max-turns safety
  net, so truly infinite loops terminate even if the agent never emits
  `[ATELIER_DONE]`.
