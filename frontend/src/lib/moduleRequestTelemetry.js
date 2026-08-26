const MODULE_PATTERNS = [
  ["spa", /^\/spa(?:\/|$)/],
  ["mice", /^\/mice(?:\/|$)/],
  ["hr", /^\/(?:hr|staff)(?:\/|$)/],
  ["marketplace", /^\/(?:marketplace|supplies-market)(?:\/|$)/],
  ["rms", /^\/(?:rms|revenue-management|pricing)(?:\/|$)/],
];

const CAPTURE_WINDOW_MS = 60_000;
const recentCaptures = new Map();

function safeParse(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function requestPath(url = "") {
  try {
    return new URL(url, "https://pms.syroce.invalid").pathname;
  } catch {
    return String(url).split("?")[0].split("#")[0];
  }
}

export function moduleForRequest(url = "") {
  const path = requestPath(url);
  return MODULE_PATTERNS.find(([, pattern]) => pattern.test(path))?.[0] || null;
}

export function tenantIdFromStorage(storage = globalThis.localStorage) {
  if (!storage) return "unknown";
  try {
    const tenant = safeParse(storage.getItem("tenant"));
    const user = safeParse(storage.getItem("user"));
    return String(
      tenant?.id || tenant?.tenant_id || tenant?.hotel_id || user?.tenant_id || "unknown",
    );
  } catch {
    return "unknown";
  }
}

export function pseudonymousTenantScope(tenantId) {
  const value = String(tenantId || "unknown");
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `t_${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function moduleFailureContext(error, storage = globalThis.localStorage) {
  const config = error?.config || {};
  const module = moduleForRequest(config.url);
  if (!module) return null;

  return {
    module,
    tenantScope: pseudonymousTenantScope(tenantIdFromStorage(storage)),
    method: String(config.method || "get").toUpperCase(),
    path: requestPath(config.url),
    status: error?.response?.status || "network",
    retryCount: Number(config._syroceRetryCount || 0),
  };
}

function shouldCaptureAlarm(context, now = Date.now()) {
  const key = `${context.tenantScope}|${context.module}|${context.method}|${context.path}|${context.status}`;
  const previous = recentCaptures.get(key) || 0;
  if (now - previous < CAPTURE_WINDOW_MS) return false;
  recentCaptures.set(key, now);
  return true;
}

export async function reportModuleRequestFailure(error) {
  const context = moduleFailureContext(error);
  if (!context || !import.meta.env.VITE_SENTRY_DSN) return;

  try {
    const Sentry = await import("@sentry/react");
    const attributes = {
      module: context.module,
      tenant_scope: context.tenantScope,
      http_status: String(context.status),
      http_method: context.method,
    };

    Sentry.metrics?.count?.("syroce.module.api_failure", 1, { attributes });

    if (!shouldCaptureAlarm(context)) return;
    Sentry.withScope((scope) => {
      scope.setLevel(context.status === 429 ? "warning" : "error");
      scope.setTags({
        subsystem: "module-api",
        severity: context.status === 429 ? "warning" : "error",
        "syroce.module": context.module,
        tenant_scope: context.tenantScope,
        "http.status_code": String(context.status),
        "http.method": context.method,
      });
      scope.setContext("module_request", {
        path: context.path,
        retry_count: context.retryCount,
      });
      scope.setFingerprint(["module-api-failure", context.module, context.path, String(context.status)]);
      // Axios hatasının headers/body alanlarını Sentry'ye taşımamak için yalnız
      // temizlenmiş mesaj ve etiketleri gönderiyoruz.
      Sentry.captureMessage("Module API request failed");
    });
  } catch {
    // Telemetry hiçbir zaman kullanıcı akışını bozmamalı.
  }
}

export function resetModuleTelemetryForTests() {
  recentCaptures.clear();
}
