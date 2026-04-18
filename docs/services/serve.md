# atelier serve (FastAPI)

!!! warning "Coming soon"
    `atelier serve` is on the roadmap and not yet implemented. This
    page is a placeholder — the final API surface may change.

## What it will do

`atelier serve` will expose the same operations as the CLI — list
conduits, start flows, inspect progress, stream logs — over a small
FastAPI HTTP service. The goal is to let other systems (a dashboard,
a chat bot, a scheduler) drive flow-atelier without shelling out.

## Planned endpoints (subject to change)

| Method   | Path                                   | Purpose                                       |
|----------|----------------------------------------|-----------------------------------------------|
| `GET`    | `/conduits`                            | List available conduits (project + global).  |
| `GET`    | `/conduits/{name}`                     | Read a single conduit definition.            |
| `POST`   | `/flows`                               | Start a new flow `{ conduit, inputs }`.      |
| `GET`    | `/flows`                               | List flows, optionally filtered by conduit. |
| `GET`    | `/flows/{flow_id}`                     | Progress for a flow.                         |
| `GET`    | `/flows/{flow_id}/logs`                | Recorded log entries.                        |
| `GET`    | `/flows/{flow_id}/logs/stream`         | SSE tail of log events.                      |

## Why serve it at all?

- **Dashboard.** A thin React/HTMX UI that shows live flow state
  across a team.
- **Chat integrations.** Slack or Discord commands that trigger a
  conduit and post the result back.
- **Scheduling.** Pair with `atelier schedule` for unattended runs.
- **Language bridges.** Anything that speaks HTTP can now start a
  flow — no Python required on the caller's side.

## Progress

Track implementation progress on the repo's issue tracker. When the
feature lands, this page will be replaced with real API documentation
and a quickstart for running `atelier serve` behind a reverse proxy.
