# Installation

## Requirements

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — used for installing `atelier` as a
  standalone CLI tool.
- **Node.js / `npx`** — only needed if you plan to use the `harness:claude-code`
  or `harness:codex` executors. The ACP adapters are fetched via `npx` on
  first use.

## Install as a global CLI

Install `atelier` globally on your PATH so it runs from any directory
(similar to how `claude` and `codex` run anywhere):

```bash
git clone https://github.com/goldenguille/flow-atelier.git
cd flow-atelier
uv tool install .
```

You can also install directly from the remote repo:

```bash
uv tool install git+https://github.com/goldenguille/flow-atelier.git
```

Upgrade or uninstall later:

```bash
uv tool upgrade flow-atelier
uv tool uninstall flow-atelier
```

## Local development

Inside a clone of the repo:

```bash
uv sync
uv run atelier --help
```

## Harness prerequisites

`harness:claude-code` and `harness:codex` launch ACP adapters published
by Zed via `npx`, so you need:

- **Node.js / `npx`** on your PATH.
- An authenticated Claude Code and/or Codex setup on this machine (the
  adapters reuse your `~/.claude` and `~/.codex` configuration, including
  auth, settings, skills, MCP servers, `CLAUDE.md`, and `AGENTS.md`).

On first use `npx` will download and cache the adapter packages:

- `@zed-industries/claude-code-acp`
- `@zed-industries/codex-acp`

!!! tip "Pin an adapter version"
    To pin a custom version or point at a locally installed adapter, set
    `ATELIER_CLAUDE_LAUNCH_CMD` / `ATELIER_CODEX_LAUNCH_CMD` to a JSON
    array of argv. See `.env.example` in the repo for templates.

## Verify the install

```bash
atelier --help
atelier init
atelier run hello --input name=world
```

If the last command prints a green `✓ greet` panel and a `flow_id:` line,
you're done.
