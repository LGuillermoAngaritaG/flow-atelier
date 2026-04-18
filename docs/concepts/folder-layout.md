# Folder layout

The `.atelier` directory lives in the working directory where `atelier`
is invoked.

```
.atelier/
├── conduits/
│   └── <conduit_name>/conduit.yaml
└── flows/
    └── <flow_id>/                       # <conduit>_<uuid8>_<YYYYMMDDTHHMMSSZ>
        ├── input.yaml
        ├── logs.json                    # append-only task execution log
        ├── progress.json                # live per-task status
        └── flows/
            └── <child_flow_id>/...      # nested tool:conduit runs
```

## Per-flow artifacts

Every run of a conduit produces a directory under `./.atelier/flows/`
named `<conduit>_<uuid8>_<UTC-timestamp>`.

| File              | What's in it                                                                 |
|-------------------|------------------------------------------------------------------------------|
| `input.yaml`      | Top-level inputs passed on the CLI, plus anything collected from HITL tasks. |
| `progress.json`   | Live per-task status (pending / running / completed / failed / skipped / cancelled). |
| `logs.json`       | Append-only event log: one entry per task iteration, with stdout/stderr/output/exit_code/duration. |
| `flows/`          | Nested flows spawned by `tool:conduit` tasks.                                |

`progress.json` is rewritten in place as tasks transition — it's what
`atelier status` reads.

`logs.json` is append-only — it's what `atelier logs` reads and what
`atelier logs --follow` tails.

## Flow ids

A flow id has three parts separated by `_`:

```
deploy_pipeline_a1b2c3d4_20260412T153004Z
└──────┬──────┘ └───┬───┘ └──────┬──────┘
    conduit       uuid8    UTC ISO timestamp
```

- The **conduit** prefix makes `atelier list flows --conduit X` cheap.
- The **uuid8** prevents collisions when multiple runs start in the same
  second.
- The **timestamp** sorts flows lexicographically by start time.

All of `atelier status`, `atelier logs`, and `atelier logs --follow`
accept a **prefix** — e.g. `atelier status deploy_pipeline_a1` — as long
as the prefix is unique.
