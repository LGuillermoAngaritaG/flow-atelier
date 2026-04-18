# atelier schedule

!!! warning "Coming soon"
    `atelier schedule` is on the roadmap and not yet implemented. This
    page is a placeholder — the final command surface may change.

## What it will do

`atelier schedule` will let you register cron-style triggers that run
a conduit on a recurring interval, without needing an external cron
daemon or a CI runner. A small scheduler loop checks the trigger
registry and invokes `atelier run` with the configured inputs when
each schedule is due.

## Planned command surface (subject to change)

```
atelier schedule create <conduit> --cron "<expr>" [--input key=value ...]
atelier schedule list
atelier schedule pause <schedule_id>
atelier schedule resume <schedule_id>
atelier schedule delete <schedule_id>
```

Schedules will live alongside conduits and flows under `.atelier/` and
will survive restarts — the scheduler loop is what picks them up.

## Why ship a scheduler?

- **Unattended runs.** "Every night, run my `backup` conduit" without
  teaching cron about your venv or PATH.
- **Human-in-the-loop friendly.** A schedule that fires a HITL-gated
  conduit can wait for the human at runtime rather than being
  cancelled as overdue.
- **Colocated with `atelier serve`.** Schedules are first-class
  resources in the planned HTTP API, so a dashboard can create and
  manage them.

## Design questions still open

- Single-process scheduler vs distributed? Probably single-process for
  the first cut, with "only run one loop per `.atelier/` dir" as the
  coordination mechanism.
- Cron expression syntax — standard 5-field, or the 6-field seconds
  variant, or interval shorthand like `every 15m`?
- Missed-tick semantics — run-once-when-back-online, or skip?

## Progress

Track implementation progress on the repo's issue tracker. When the
feature lands, this page will be replaced with real docs and a
quickstart for registering schedules.
