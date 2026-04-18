---
hide:
  - navigation
---

# flow-atelier

**flow-atelier** is a CLI and async workflow engine for running reproducible
DAG-based workflows called **conduits**. A single run of a conduit is a
**flow**. Tasks whose dependencies are satisfied run concurrently via
`asyncio`, subject to a conduit-level concurrency cap.

Each task is dispatched to one of five executors:

| Tool                  | What it runs                                                     |
|-----------------------|------------------------------------------------------------------|
| `tool:bash`           | a shell command (via `asyncio.create_subprocess_shell`)          |
| `tool:hitl`           | prompts a human on stdin for one or more named inputs            |
| `tool:conduit`        | another conduit, as a nested flow                                |
| `harness:claude-code` | Claude Code via the [ACP](https://agentclientprotocol.com) adapter |
| `harness:codex`       | OpenAI Codex via the ACP adapter                                 |

Harnesses speak the **Agent Client Protocol** (ACP) over stdio, so they get
real bidirectional interaction — the agent can ask for permission, ask the
user a free-form question mid-turn, or run a multi-turn conversation.

---

## Where to go next

<div class="grid cards" markdown>

- :material-rocket-launch: **[Install →](getting-started/installation.md)**

    Get `atelier` on your PATH with a single `uv tool install`.

- :material-play-circle: **[Quickstart →](getting-started/quickstart.md)**

    Scaffold a project, run your first conduit, and inspect a flow in under
    a minute.

- :material-book-open-variant: **[Conduit reference →](reference/conduit.md)**

    The full YAML spec — tasks, tools, templating, conditions, timeouts.

- :material-lightbulb-on: **[Examples →](examples/index.md)**

    Worked examples covering AI code review, deploy pipelines with human
    approval gates, parallel batch processing, and more.

</div>

---

## Design philosophy

- **Reproducible by default.** Every flow is a directory on disk with its
  inputs, per-task logs, and live progress — inspectable after the fact
  with `atelier status` and `atelier logs`.
- **Agents are first-class tasks.** Claude Code and Codex are not wrapped
  shell calls — they speak ACP, so they can request permission, stream
  tool calls, and participate in multi-turn conversations from inside a
  conduit.
- **Humans are first-class tasks.** `tool:hitl` turns any dependency graph
  into a workflow with approval gates, free-form prompts, and data that
  flows downstream.
- **Small core.** The async DAG engine depends only on base classes for
  storage and executors, so new tools or backends slot in without
  touching the scheduler.
