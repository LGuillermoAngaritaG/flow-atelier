# Parallel batch processing

Fan-out + fan-in with `max_concurrency` and `repeat`. Good shape for
batch data jobs, parallel API calls, or any "do N things, then
aggregate" workflow.

## Scenario

You have a list of shards you want to process in parallel, with a cap
on how many run concurrently to avoid hammering a downstream service.
Once all shards finish, an aggregation step writes a summary.

## The conduit

```yaml title=".atelier/conduits/batch-shards/conduit.yaml"
name: batch-shards
description: Process 4 shards in parallel, then aggregate
max_concurrency: 2

tasks:
  - setup:
      description: Create the work directory
      task: "mkdir -p /tmp/shards && rm -f /tmp/shards/*.out"
      tool: tool:bash
      depends_on: []

  - shard_0:
      description: Process shard 0
      task: "sleep 2 && echo shard-0-done > /tmp/shards/0.out"
      tool: tool:bash
      depends_on: [setup]

  - shard_1:
      description: Process shard 1
      task: "sleep 2 && echo shard-1-done > /tmp/shards/1.out"
      tool: tool:bash
      depends_on: [setup]

  - shard_2:
      description: Process shard 2
      task: "sleep 2 && echo shard-2-done > /tmp/shards/2.out"
      tool: tool:bash
      depends_on: [setup]

  - shard_3:
      description: Process shard 3
      task: "sleep 2 && echo shard-3-done > /tmp/shards/3.out"
      tool: tool:bash
      depends_on: [setup]

  - aggregate:
      description: Combine all shard outputs
      task: "cat /tmp/shards/*.out | sort > /tmp/shards/summary.txt && cat /tmp/shards/summary.txt"
      tool: tool:bash
      depends_on: [shard_0, shard_1, shard_2, shard_3]
```

## Run it

```bash
atelier run batch-shards
```

## What you should see

- `setup` runs first.
- With `max_concurrency: 2`, two shards start, then the next two start
  as each finishes. Total wall time is ~4s, not ~8s.
- `aggregate` waits until all four shards complete, then emits a summary.

You can watch the parallel execution live by running `atelier logs <id>
--follow` in another terminal.

## Why `max_concurrency` matters

Without the cap, all four shards would run at once — fine for CPU
work, dangerous for rate-limited downstreams (external APIs, shared
databases). Setting `max_concurrency` to a small number gives you a
consistent, predictable load profile without hand-coding pool logic.

## Variations

### Retry flaky shards

```yaml
- shard_0:
    task: "flaky-command --shard 0"
    tool: tool:bash
    depends_on: [setup]
    repeat: 3
```

`repeat: 3` runs the task up to 3 times **sequentially** — useful for
retry semantics. The engine treats each iteration as a separate entry
in `logs.json`.

!!! note "repeat vs parallel fan-out"
    `repeat` is sequential on a single task. For parallel fan-out,
    declare multiple sibling tasks (`shard_0`, `shard_1`, …) as shown
    above. Conduits have no `for-each` primitive — the parallel shape is
    the explicit task list.

### Conditional aggregate

If you want `aggregate` to run only when at least one shard succeeded,
add a "checker" task between the shards and aggregate that emits a
canonical token, and condition `aggregate` on matching that token.

### Fail-fast vs continue

By default, one failing shard cancels the remaining siblings and marks
`aggregate` as cancelled. To keep independent shards running even on
failure, split the branches so they don't share the same cancel point
(e.g. run each shard through its own nested conduit via `tool:conduit`).
