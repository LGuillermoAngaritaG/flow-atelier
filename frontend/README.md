# flow-atelier

A web UI for building, scheduling, and running conduit workflows — DAG-based pipelines that orchestrate bash commands, AI coding agents (Claude Code, Codex, Copilot, Cursor), nested conduits, and human-in-the-loop approval gates.

## Features

- **Dashboard** — browse conduits, view run history, and manage scheduled jobs
- **Designer** — visual DAG editor for authoring conduit workflows with drag-and-drop node placement and dependency edges
- **Kanban** — task board for tracking conduit runs across columns (todo → in progress → done) with live log streaming and HITL prompts

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** — dev server and bundler
- **Tailwind CSS v4** — utility-first styling
- **Zustand** — state management
- **XYFlow** — canvas/DAG rendering in the designer
- **dnd-kit** — drag-and-drop in the kanban board
- **Radix UI** — accessible primitives (dialogs, selects, tooltips, etc.)
- **Vitest** — unit tests
- **Playwright** — end-to-end tests

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **npm** (or your preferred package manager)

### Install

```bash
npm install
```

### Environment Variables

A `.env` file in the project root (gitignored) is optional — the app runs with the defaults below, which mirror `.env.example`. Set a variable in `.env` to override it:

| Variable             | Description                              | Default                  |
|----------------------|------------------------------------------|--------------------------|
| `VITE_USE_MOCK_API`  | `"true"` for simulated backend data      | `true`                   |
| `VITE_BACKEND_URL`   | Base URL for the backend API             | `http://localhost:8080`  |
| `VITE_API_TOKEN`     | Bearer token sent to the backend         | `secret-key`             |

Mock mode is on by default. To hit a real backend, disable mock mode and point at it:

```
VITE_USE_MOCK_API=false
VITE_BACKEND_URL=http://localhost:8080
VITE_API_TOKEN=your-token
```

### Run the dev server

```bash
npm run dev
```

Opens at [http://localhost:5173](http://localhost:5173).

### Build for production

```bash
npm run build
```

Output goes to `dist/`.

### Sync build to the backend

The production build needs to land in the backend's `dist/` folder so it can serve the frontend. You can do this manually:

```bash
npm run build
rm -rf /path/to/backend/dist
cp -r dist /path/to/backend/dist
```

Or use the Makefile (set `BACKEND_PATH` to your backend root):

```bash
# macOS / Linux
make sync BACKEND_PATH=/path/to/backend

# Windows (requires Git Bash)
make sync BACKEND_PATH=C:/path/to/backend
```

### Preview the production build

```bash
npm run preview
```

## Project Structure

```
src/
├── components/ui/     # Shared UI primitives (button, dialog, select, etc.)
├── context/           # React context providers (theme)
├── features/
│   ├── dashboard/     # Dashboard page — conduits, history, schedules
│   ├── designer/      # Visual DAG editor — nodes, edges, palette, inspector
│   └── kanban/        # Task board — columns, cards, live task runner
├── hooks/             # Shared React hooks
├── layout/            # App shell — top bar, footer, theme toggle
├── lib/               # Small utilities (cn)
├── pages/             # Route-level page components
├── runner/            # Task execution engine — mock timing, HITL gating, log streaming
├── services/
│   ├── api/           # Backend API calls
│   ├── mock/          # Fixture data for mock mode
│   └── storage/       # LocalStorage persistence
├── styles/            # Global CSS
├── types/             # Shared TypeScript types
└── utils/             # Pure helpers (format, yaml)
```

## Scripts

| Command              | Description                        |
|----------------------|------------------------------------|
| `npm run dev`        | Start dev server (port 5173)       |
| `npm run build`      | Type-check and build for production|
| `npm run preview`    | Serve the production build locally |
| `npm run test`       | Run unit tests once                |
| `npm run test:watch` | Run unit tests in watch mode       |
| `npm run test:coverage` | Run tests with coverage report  |

## How It Works

The app has two operating modes controlled by `VITE_USE_MOCK_API`:

- **Mock mode** — simulates the backend with fixture data and deterministic timing. Conduits run through their tasks with realistic delays and canned log output. No backend required.
- **Real mode** — connects to a flow-atelier backend via REST API. Tasks are submitted and tracked server-side with real execution logs streamed back.

The **runner engine** (`src/runner/`) drives task execution in both modes: it walks the conduit's DAG of tasks, handles human-in-the-loop gates (pausing for user input), streams log lines into the kanban cards, and moves tasks through columns as they progress.
