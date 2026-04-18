# Examples

Each example is a complete, working conduit that demonstrates a
different feature or pattern. Copy-paste any of them into
`.atelier/conduits/<name>/conduit.yaml` and run with
`atelier run <name> --input ...`.

<div class="grid cards" markdown>

- :material-hand-wave: **[Hello world →](hello-world.md)**

    Minimal single-task conduit. Shows the `tool:bash` executor and the
    `{{inputs.x}}` template.

- :material-robot: **[AI code review with rollback →](ai-code-review.md)**

    A Claude Code harness task produces a verdict; conditional deps
    branch to `deploy` or `rollback`.

- :material-rocket: **[Deploy pipeline with HITL gate →](deploy-pipeline.md)**

    Clone → test (with retries) → AI review → human approval → deploy,
    with rollback on failure.

- :material-call-split: **[Parallel batch processing →](parallel-batch.md)**

    Fan-out + fan-in with `max_concurrency` and `repeat`. Good shape
    for batch jobs, data ingestion, or flaky test reruns.

- :material-message-processing: **[Interactive harness session →](interactive-harness.md)**

    A multi-turn `harness:claude-code` task that pairs with you on a
    feature, ending when the agent emits `[ATELIER_DONE]`.

- :material-file-tree: **[Nested conduits →](nested-conduits.md)**

    A parent conduit invokes `tool:conduit` to run a reusable child
    conduit with its own inputs.

</div>

---

## How to follow along

Every example page includes:

1. The **scenario** — what the conduit is modelling.
2. The **full `conduit.yaml`** — copy-pasteable.
3. The **run command** with example inputs.
4. **What you should see** — the expected terminal output and the
   on-disk artifacts.
5. **Variations** — small tweaks that demonstrate related features.

If you'd like to run an example but don't want to touch your global
conduits, scope it to your project with `atelier init` and drop the
YAML under `./.atelier/conduits/<name>/conduit.yaml`.
