# Nested conduits

`tool:conduit` runs another conduit as a child flow, with its own
inputs and its own set of artifacts under the parent flow's directory.
Use it to extract reusable sub-workflows without forcing every user
into a single monolithic conduit.

## Scenario

You have a `deploy_to_env` sub-workflow — upload, migrate, smoke-test,
flip-traffic — that runs identically for staging and prod. You want
the parent pipeline to **call** it with an env argument rather than
duplicating the four tasks inline.

## The child conduit

```yaml title=".atelier/conduits/deploy_to_env/conduit.yaml"
name: deploy_to_env
description: Upload, migrate, smoke-test, flip traffic
inputs:
  target_env: Target environment
  build_path: Path to the built artifact

tasks:
  - upload:
      description: Upload to the target env
      task: "./bin/upload {{inputs.build_path}} {{inputs.target_env}}"
      tool: tool:bash
      depends_on: []

  - migrate:
      description: Run database migrations
      task: "./bin/migrate --env {{inputs.target_env}}"
      tool: tool:bash
      depends_on: [upload]

  - smoke:
      description: Smoke test the new deploy
      task: "./bin/smoke-test --env {{inputs.target_env}}"
      tool: tool:bash
      depends_on: [migrate]

  - flip:
      description: Flip traffic to the new deploy
      task: "./bin/flip-traffic --env {{inputs.target_env}}"
      tool: tool:bash
      depends_on: [smoke]
```

## The parent conduit

```yaml title=".atelier/conduits/release/conduit.yaml"
name: release
description: Build once, deploy to staging then prod
inputs:
  branch: Branch to release

tasks:
  - build:
      description: Build the artifact
      task: "./bin/build --branch {{inputs.branch}}"
      tool: tool:bash
      depends_on: []

  - deploy_staging:
      description: Run deploy_to_env for staging
      task: deploy_to_env
      tool: tool:conduit
      depends_on: [build]
      inputs:
        target_env: staging
        build_path: /tmp/build

  - smoke_staging:
      description: Post-deploy staging check
      task: "./bin/e2e --env staging"
      tool: tool:bash
      depends_on: [deploy_staging]

  - approve_prod:
      description: Human approval for prod rollout
      task: "Staging smoke passed. Roll forward to prod?"
      tool: tool:hitl
      depends_on: [smoke_staging]
      inputs:
        confirm: "Type 'yes' to deploy to prod"

  - deploy_prod:
      description: Run deploy_to_env for prod
      task: deploy_to_env
      tool: tool:conduit
      depends_on:
        - approve_prod.output.match(confirm:\s*yes)
      inputs:
        target_env: prod
        build_path: /tmp/build
```

## Run it

```bash
atelier run release --input branch=main
```

## What happens on disk

Nested flows live **under the parent flow's directory**:

```
.atelier/flows/release_abc123_20260412T170000Z/
├── input.yaml                       # parent inputs
├── progress.json
├── logs.json
└── flows/
    ├── deploy_to_env_f1e2d3c4_20260412T170015Z/
    │   ├── input.yaml               # { target_env: staging, build_path: /tmp/build }
    │   ├── progress.json
    │   └── logs.json
    └── deploy_to_env_b9a8c7d6_20260412T170045Z/
        ├── input.yaml               # { target_env: prod, build_path: /tmp/build }
        ├── progress.json
        └── logs.json
```

Each child flow is a fully-formed flow you can inspect with
`atelier status` and `atelier logs` — they're not "lost" inside the
parent.

## Why this shape works

- **Reusable sub-workflows.** Anyone can call `deploy_to_env` with
  their own inputs — from another conduit, or directly via
  `atelier run deploy_to_env --input target_env=...`.
- **Inputs are explicit.** The parent passes inputs through the
  `inputs:` block on the `tool:conduit` task. No environment-variable
  implicit sharing.
- **Artifacts are traceable.** The child flow directory is nested under
  the parent's, so `atelier list flows` still shows the parent as the
  top-level entry and you can drill in.

## Variations

### Child conduit lives in a different scope

The parent always sees a conduit via `project-first, global-fallback`
lookup. So `tool:conduit: deploy_to_env` will find a project copy if
one exists, otherwise a global copy. You can keep `deploy_to_env`
globally and override it per-project.

### Pass upstream output as a child input

```yaml
- build:
    task: "./bin/build && echo $(realpath /tmp/build/app.tar.gz)"
    tool: tool:bash
    depends_on: []

- deploy_staging:
    task: deploy_to_env
    tool: tool:conduit
    depends_on: [build]
    inputs:
      target_env: staging
      build_path: "{{build.output}}"
```
