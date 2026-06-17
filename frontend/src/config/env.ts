/**
 * App configuration from Vite env vars. Values in `.env` / `.env.local` override
 */
const env = import.meta.env;

// Default to the real API; mocks are opt-in via VITE_USE_MOCK_API=true.
export const USE_MOCK = (env.VITE_USE_MOCK_API ?? "false") === "true";
// The bundled SPA is served by the FastAPI app itself, so the backend lives
// at whatever origin the page loaded from. Deriving BASE_URL at runtime keeps
// the frontend in sync with any `atelier serve --port` automatically.
// VITE_BACKEND_URL overrides this (e.g. a dev server on a separate port).
export const BASE_URL = env.VITE_BACKEND_URL ?? window.location.origin;
export const API_TOKEN = env.VITE_API_TOKEN ?? "secret-key";
