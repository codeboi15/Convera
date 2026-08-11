/**
 * Single source of truth for frontend configuration.
 *
 * Every environment-dependent value is read here and nowhere else, so nothing
 * is hardcoded across the app. Next.js inlines `NEXT_PUBLIC_*` at build time,
 * so these must be referenced as full literals (not computed keys).
 *
 * Only non-secret values belong here — anything `NEXT_PUBLIC_` is visible in
 * the browser bundle. Secrets stay on the backend.
 */

const DEV_API = "http://localhost:8000";

function trimSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

/** Base URL of the FastAPI backend (REST). */
export const API_URL = trimSlash(process.env.NEXT_PUBLIC_API_URL || DEV_API);

/** Socket.IO endpoint — defaults to the API host when not set separately. */
export const SOCKET_URL = trimSlash(
  process.env.NEXT_PUBLIC_SOCKET_URL || process.env.NEXT_PUBLIC_API_URL || DEV_API,
);

/** Path Socket.IO is mounted on by the backend ASGI app. */
export const SOCKET_PATH = "/socket.io";

/** Public origin of this app; used to build widget install snippets. */
export const APP_URL = trimSlash(
  process.env.NEXT_PUBLIC_APP_URL ||
    (typeof window !== "undefined" ? window.location.origin : ""),
);

/** Shared realtime client tuning. */
export const SOCKET_OPTIONS = {
  path: SOCKET_PATH,
  transports: ["websocket" as const],
  reconnection: true,
  reconnectionDelay: 500,
  reconnectionDelayMax: 5000,
};

/** Heartbeat interval (ms) that keeps presence TTLs fresh. */
export const PRESENCE_HEARTBEAT_MS = 25_000;

export const config = {
  apiUrl: API_URL,
  socketUrl: SOCKET_URL,
  socketPath: SOCKET_PATH,
  appUrl: APP_URL,
};

export default config;
