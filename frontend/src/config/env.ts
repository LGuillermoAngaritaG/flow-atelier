/**
 * App configuration from Vite env vars. Values in `.env` / `.env.local` override
 */
const env = import.meta.env;

// Default to the real API; mocks are opt-in via VITE_USE_MOCK_API=true.
export const USE_MOCK = (env.VITE_USE_MOCK_API ?? "false") === "true";
export const BASE_URL = env.VITE_BACKEND_URL ?? "http://localhost:8080";
// No default token: a missing VITE_API_TOKEN must fail loudly, not ship a
// guessable shared credential. Requests simply send no Authorization header.
export const API_TOKEN = env.VITE_API_TOKEN ?? "";

if (!USE_MOCK && !API_TOKEN) {
  console.warn(
    "[config] VITE_API_TOKEN is not set — API requests will be sent without authentication.",
  );
}
