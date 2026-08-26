import { reportModuleRequestFailure } from "@/lib/moduleRequestTelemetry";

const RETRYABLE_STATUS = new Set([408, 425, 429, 502, 503, 504]);
const SAFE_METHODS = new Set(["get", "head"]);
const DEFAULT_RETRIES = 2;
const MAX_RETRY_DELAY_MS = 60_000;

export function parseRetryAfter(value, now = Date.now()) {
  if (value == null || value === "") return null;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.round(seconds * 1000);
  }

  const timestamp = Date.parse(String(value));
  if (Number.isNaN(timestamp)) return null;
  return Math.max(0, timestamp - now);
}

function retryAfterHeader(headers) {
  if (!headers) return null;
  if (typeof headers.get === "function") {
    return headers.get("retry-after") ?? headers.get("Retry-After");
  }
  return headers["retry-after"] ?? headers["Retry-After"] ?? null;
}

export function shouldRetryRequest(error) {
  const config = error?.config || {};
  const method = String(config.method || "get").toLowerCase();
  if (!SAFE_METHODS.has(method) || config._skipRetry) return false;
  if (typeof navigator !== "undefined" && navigator.onLine === false) return false;

  const status = error?.response?.status;
  if (status == null) return error?.code !== "ERR_CANCELED";
  return RETRYABLE_STATUS.has(status);
}

export function retryDelayMs(error, attempt, {
  now = Date.now(),
  random = Math.random,
  maxDelayMs = MAX_RETRY_DELAY_MS,
} = {}) {
  const retryAfter = parseRetryAfter(retryAfterHeader(error?.response?.headers), now);
  if (retryAfter != null) return Math.min(retryAfter, maxDelayMs);

  const exponential = 350 * (2 ** Math.max(0, attempt - 1));
  const jitter = Math.floor(random() * 250);
  return Math.min(exponential + jitter, maxDelayMs);
}

export function isReportableModuleReadFailure(error) {
  const method = String(error?.config?.method || "get").toLowerCase();
  if (!SAFE_METHODS.has(method)) return false;
  const status = error?.response?.status;
  return status == null || status === 403 || status === 404 || status === 429 || status >= 500;
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function installAxiosResilience(httpClient, {
  defaultRetries = DEFAULT_RETRIES,
  sleep = wait,
  random = Math.random,
  reportFailure = reportModuleRequestFailure,
} = {}) {
  if (httpClient.__syroceResilienceInstalled) return;
  httpClient.__syroceResilienceInstalled = true;

  httpClient.interceptors.response.use(
    (response) => response,
    async (error) => {
      const config = error?.config || {};
      const retryCount = Number(config._syroceRetryCount || 0);
      const maxRetries = Number.isFinite(config._maxRetries)
        ? Math.max(0, config._maxRetries)
        : defaultRetries;

      if (shouldRetryRequest(error) && retryCount < maxRetries) {
        const nextAttempt = retryCount + 1;
        config._syroceRetryCount = nextAttempt;
        await sleep(retryDelayMs(error, nextAttempt, { random }));
        return httpClient.request(config);
      }

      if (isReportableModuleReadFailure(error) && !config._syroceFailureReported) {
        config._syroceFailureReported = true;
        // Sentry yüklenmesini/iletimini kullanıcı yanıtının önüne koyma.
        Promise.resolve(reportFailure(error)).catch(() => {});
      }
      return Promise.reject(error);
    },
  );
}
