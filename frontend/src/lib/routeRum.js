const CRITICAL_ROUTES = new Set([
  "/app/dashboard",
  "/app/pms",
  "/app/reservation-calendar",
  "/app/raporlar",
  "/app/channel-manager",
]);

const RUM_URL = "/observability/rum/events";
const MAX_ROUTE_AGE_MS = 10 * 60 * 1000;
const MIN_ROUTE_AGE_MS = 250;

const percentile = (values, p) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * p) - 1)];
};

export function isRumEnabled() {
  if (typeof window === "undefined" || !import.meta.env.PROD) return false;
  const configured = Number(import.meta.env.VITE_RUM_SAMPLE_RATE ?? 0.1);
  return Number.isFinite(configured) && configured > 0 && Math.random() < Math.min(configured, 1);
}

// No URL query, user ID, tenant ID, request body or error message leaves the
// browser. Identity and tenant scope are derived from the authenticated cookie
// on the API; the payload is deliberately operational aggregate-only.
export class RouteRum {
  constructor({ enabled = isRumEnabled(), now = () => performance.now() } = {}) {
    this.enabled = enabled;
    this.now = now;
    this.current = null;
    this.observers = [];
  }

  start(pathname) {
    this.flush();
    if (!this.enabled || !CRITICAL_ROUTES.has(pathname)) return;

    this.current = { pathname, startedAt: this.now(), lcp: null, inp: null, cls: 0 };
    this.observe("largest-contentful-paint", (entry) => {
      if (this.current) this.current.lcp = Math.round(entry.startTime);
    });
    this.observe("event", (entry) => {
      if (this.current && entry.interactionId && entry.duration) this.current.inp = Math.max(this.current.inp || 0, Math.round(entry.duration));
    }, { durationThreshold: 40 });
    this.observe("layout-shift", (entry) => {
      if (this.current && !entry.hadRecentInput) this.current.cls += entry.value || 0;
    });
  }

  observe(type, onEntry, options = {}) {
    try {
      const observer = new PerformanceObserver((list) => list.getEntries().forEach(onEntry));
      observer.observe({ type, buffered: true, ...options });
      this.observers.push(observer);
    } catch { /* unsupported PerformanceObserver entry type */ }
  }

  flush() {
    const current = this.current;
    this.observers.forEach((observer) => observer.disconnect());
    this.observers = [];
    this.current = null;
    if (!current) return;

    const routeDurationMs = Math.round(this.now() - current.startedAt);
    // React StrictMode intentionally mounts/unmounts effects once in development;
    // short-lived transitions should not influence a real-user percentile.
    if (routeDurationMs < MIN_ROUTE_AGE_MS || routeDurationMs > MAX_ROUTE_AGE_MS) return;
    const resources = performance.getEntriesByType("resource");
    const api = resources.filter((entry) => /\/api\//.test(entry.name));
    const apiDurations = api.map((entry) => Math.round(entry.duration));
    const payload = JSON.stringify({ events: [{
      route: current.pathname,
      route_duration_ms: routeDurationMs,
      lcp_ms: current.lcp,
      inp_ms: current.inp,
      cls: Math.round(current.cls * 1000) / 1000,
      api_count: apiDurations.length,
      api_p95_ms: percentile(apiDurations, 0.95),
    }] });
    try {
      // Beacon avoids delaying navigation/logout. Cookies provide auth; no token
      // is copied to the payload or URL.
      const rawBackendUrl = import.meta.env.VITE_BACKEND_URL || "/api";
      const backendUrl = rawBackendUrl.replace(/\/$/, "").endsWith("/api")
        ? rawBackendUrl.replace(/\/$/, "")
        : `${rawBackendUrl.replace(/\/$/, "")}/api`;
      navigator.sendBeacon(backendUrl + RUM_URL, new Blob([payload], { type: "application/json" }));
    } catch { /* telemetry must never affect the hotel workflow */ }
  }
}
