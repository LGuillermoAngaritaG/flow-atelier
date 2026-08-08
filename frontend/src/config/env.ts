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
// The API token is read at *runtime*, not baked in at build time. The SPA in
// the wheel is compiled once and shipped to everyone, so a build-time constant
// is empty in every installed copy — setting ATELIER_API_TOKEN on the server
// used to 401 the bundled UI out of its own API with no way to authenticate.
// VITE_API_TOKEN still seeds it, for a dev server pointed at a remote backend.
//
// sessionStorage, not localStorage: the token dies with the tab rather than
// outliving the session on a shared machine. It is deliberately not persisted
// to disk anywhere, and never sent to an origin other than BASE_URL.
const TOKEN_KEY = "atelier:api-token";

export function getApiToken(): string {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) ?? env.VITE_API_TOKEN ?? "";
  } catch {
    // Storage can throw outright (Safari private mode, disabled cookies).
    return env.VITE_API_TOKEN ?? "";
  }
}

export function setApiToken(token: string): void {
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Non-fatal: the caller still sends the token on the retry it just made,
    // the user simply gets asked again on the next cold call.
  }
}
