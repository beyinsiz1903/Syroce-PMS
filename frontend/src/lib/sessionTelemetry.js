import { isRumEnabled } from "@/lib/routeRum";

const SESSION_EVENTS_URL = "/observability/rum/session-events";

// Session telemetry is intentionally aggregate-only. The server derives the
// user and tenant from the authenticated cookie; no email, ID, token, route
// query or failure message is ever sent by the browser.
export function recordSessionEvent(event, { enabled = isRumEnabled() } = {}) {
  if (!enabled || typeof navigator === "undefined" || typeof Blob === "undefined") return false;
  const payload = JSON.stringify({ event });
  try {
    const rawBackendUrl = import.meta.env.VITE_BACKEND_URL || "/api";
    const backendUrl = rawBackendUrl.replace(/\/$/, "").endsWith("/api")
      ? rawBackendUrl.replace(/\/$/, "")
      : `${rawBackendUrl.replace(/\/$/, "")}/api`;
    return navigator.sendBeacon(backendUrl + SESSION_EVENTS_URL, new Blob([payload], { type: "application/json" }));
  } catch {
    return false;
  }
}
