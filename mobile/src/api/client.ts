import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'syroce.auth.token';
const REFRESH_TOKEN_KEY = 'syroce.auth.refresh_token';
const TOKEN_ISSUED_AT_KEY = 'syroce.auth.token_issued_at';
const PUSH_DEVICE_ID_KEY = 'syroce.push.device_id';
const BIOMETRIC_PREF_KEY = 'syroce.biometric.enabled';

// V3: backend mints 15-min access tokens (configured via JWT_EXPIRATION_HOURS=0.25
// or interpreted from token exp claim). We refresh proactively at the 12-min
// mark so a click never lands during the brief window where the access token
// has just expired but rotation hasn't happened yet.
const ACCESS_TOKEN_LIFETIME_MS = 15 * 60 * 1000;
const REFRESH_GRACE_MS = 3 * 60 * 1000; // refresh when <3 min remaining

// Backend autoscale cold-start: the warm-up gate returns 503 "Server is
// warming up" (with Retry-After) for /api/* until bootstrap finishes. The
// request is rejected BEFORE it reaches the handler, so retrying is safe for
// every method (including POST /login). Bounded so a genuine outage still
// fails fast instead of hanging the UI forever.
const WARMUP_MAX_RETRIES = 8;
const WARMUP_DEFAULT_DELAY_MS = 4000;
const WARMUP_MAX_DELAY_MS = 6000;

type ExpoConfigLike = { hostUri?: string };
type LegacyManifestLike = { debuggerHost?: string };

function readHostUri(): string | undefined {
  const cfg = Constants.expoConfig as ExpoConfigLike | null | undefined;
  if (cfg?.hostUri) return cfg.hostUri;
  const legacy = (Constants as unknown as { manifest?: LegacyManifestLike }).manifest;
  return legacy?.debuggerHost;
}

export function getApiUrl(): string {
  const url = process.env.EXPO_PUBLIC_API_URL;
  if (url && url.length > 0) return url.replace(/\/$/, '');
  const hostUri = readHostUri();
  if (hostUri) {
    const host = String(hostUri).split(':')[0];
    return `http://${host}:8000`;
  }
  return 'http://localhost:8000';
}

export function getQuickIdUrl(): string {
  const url = process.env.EXPO_PUBLIC_QUICKID_URL;
  if (url && url.length > 0) return url.replace(/\/$/, '');
  const api = getApiUrl();
  return api.replace(/:8000(\/|$)/, ':8099$1').replace(/:8000$/, ':8099');
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function setToken(token: string | null): Promise<void> {
  if (token) {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    await SecureStore.setItemAsync(TOKEN_ISSUED_AT_KEY, String(Date.now()));
  } else {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(TOKEN_ISSUED_AT_KEY);
  }
}

export async function getRefreshToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function setRefreshToken(token: string | null): Promise<void> {
  if (token) {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token);
  } else {
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  }
}

async function getTokenIssuedAt(): Promise<number | null> {
  try {
    const raw = await SecureStore.getItemAsync(TOKEN_ISSUED_AT_KEY);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/**
 * Wipe every locally-stored credential / cache key on logout so a stolen
 * device cannot resume the session and so the next user starts clean.
 * Called by `auth.logout` and by the auth store on hard reset.
 *
 * V3 spec: "tüm secure store tamamen temizlenir." We therefore drop the
 * biometric preference too — a fresh session re-prompts the user to
 * opt in, which is the conservative privacy default.
 */
export async function clearAllAuthStorage(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => {}),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY).catch(() => {}),
    SecureStore.deleteItemAsync(TOKEN_ISSUED_AT_KEY).catch(() => {}),
    SecureStore.deleteItemAsync(PUSH_DEVICE_ID_KEY).catch(() => {}),
    SecureStore.deleteItemAsync(BIOMETRIC_PREF_KEY).catch(() => {}),
  ]);
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export type QueryValue = string | number | boolean | undefined | null;

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  auth?: boolean;
  headers?: Record<string, string>;
  /** Internal flag – set by the retry path so we never recurse indefinitely. */
  _retried?: boolean;
};

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const base = getApiUrl();
  let url = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? '' : '/'}${path}`;
  if (query) {
    const params = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    if (params.length) url += (url.includes('?') ? '&' : '?') + params.join('&');
  }
  return url;
}

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== 'undefined' && body instanceof FormData;
}

// ---------------------------------------------------------------------------
// JWT refresh interceptor
// ---------------------------------------------------------------------------
// We support two refresh trigger points:
//   1. Proactive: if the cached "issued at" timestamp + lifetime < now+grace,
//      refresh BEFORE making the request. Avoids racing against a 401 in the
//      middle of a critical user action.
//   2. Reactive: if a request still comes back 401 and we have a refresh
//      token, try to rotate once and replay the original request.
// Concurrent callers share a single in-flight promise so we never fire two
// refresh requests in parallel (which would race on revoke + lose one token).

let _refreshInFlight: Promise<string | null> | null = null;

async function _doRefresh(): Promise<string | null> {
  // Lazy import to avoid the cycle (`auth.ts` imports `client.ts`).
  const { refreshAccessToken } = await import('./auth');
  try {
    const res = await refreshAccessToken();
    return res?.access_token || null;
  } catch {
    return null;
  }
}

async function refreshIfNeeded(force: boolean): Promise<string | null> {
  if (_refreshInFlight) return _refreshInFlight;
  if (!force) {
    const issuedAt = await getTokenIssuedAt();
    if (!issuedAt) return null;
    const remaining = ACCESS_TOKEN_LIFETIME_MS - (Date.now() - issuedAt);
    if (remaining > REFRESH_GRACE_MS) return null;
  }
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;
  _refreshInFlight = _doRefresh().finally(() => {
    _refreshInFlight = null;
  });
  return _refreshInFlight;
}

// Sleep that resolves after `ms` OR rejects immediately if the caller's
// AbortSignal fires — so a warm-up backoff never holds the request open after
// the consumer (screen unmount / user cancel) has aborted it.
function warmupBackoff(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError(0, 'NETWORK', { message: 'aborted' }));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new ApiError(0, 'NETWORK', { message: 'aborted' }));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener?.('abort', onAbort, { once: true });
  });
}

export async function apiRequest<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, opts.query);
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(opts.headers || {}),
  };
  if (opts.body && !isFormData(opts.body)) {
    headers['Content-Type'] = 'application/json';
  }

  const isAuthCall = opts.auth !== false;
  if (isAuthCall) {
    // Proactive rotate when the access token is close to expiring.
    if (!opts._retried && path !== '/api/auth/refresh-token' && path !== '/api/auth/login') {
      await refreshIfNeeded(false).catch(() => null);
    }
    const token = await getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (opts.body !== undefined && opts.body !== null) {
    body = isFormData(opts.body) ? opts.body : JSON.stringify(opts.body);
  }

  let res: Response;
  let text = '';
  let warmupAttempts = 0;
  for (;;) {
    try {
      res = await fetch(url, {
        method: opts.method || 'GET',
        headers,
        body,
        signal: opts.signal,
      });
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'network_error';
      throw new ApiError(0, 'NETWORK', { message });
    }
    text = await res.text();
    // Retry ONLY the backend cold-start warm-up gate, identified by its exact
    // 503 signature ({"status":"starting", ... "Server is warming up"}). That
    // response is produced BEFORE the request reaches any handler, so replaying
    // it is side-effect-free even for POST/PATCH/DELETE. A genuine handler-level
    // 503 has a different body and is NOT retried — no duplicate side effects.
    const isWarmupGate =
      res.status === 503 &&
      (text.includes('"status":"starting"') || text.includes('warming up'));
    if (isWarmupGate && warmupAttempts < WARMUP_MAX_RETRIES) {
      const ra = Number(res.headers.get('retry-after'));
      const delay =
        Number.isFinite(ra) && ra > 0
          ? Math.min(ra * 1000, WARMUP_MAX_DELAY_MS)
          : WARMUP_DEFAULT_DELAY_MS;
      warmupAttempts += 1;
      await warmupBackoff(delay, opts.signal); // rejects immediately on abort
      continue;
    }
    break;
  }

  // Reactive refresh: 401 once → rotate → replay original request once.
  if (
    res.status === 401 &&
    isAuthCall &&
    !opts._retried &&
    path !== '/api/auth/refresh-token' &&
    path !== '/api/auth/login'
  ) {
    const fresh = await refreshIfNeeded(true).catch(() => null);
    if (fresh) {
      return apiRequest<T>(path, { ...opts, _retried: true });
    }
  }

  // `text` was already read inside the warm-up loop above (body is single-use).
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    let detail: string = res.statusText || 'request_failed';
    if (data && typeof data === 'object') {
      const obj = data as { detail?: unknown; message?: unknown };
      if (typeof obj.detail === 'string') detail = obj.detail;
      else if (typeof obj.message === 'string') detail = obj.message;
      else if (obj.detail !== undefined) detail = JSON.stringify(obj.detail);
    }
    throw new ApiError(res.status, detail, data);
  }
  return data as T;
}

export const api = {
  get: <T = unknown>(path: string, query?: RequestOptions['query']) =>
    apiRequest<T>(path, { query }),
  post: <T = unknown>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'POST', body }),
  put: <T = unknown>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PUT', body }),
  patch: <T = unknown>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body }),
  del: <T = unknown>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
};

// ---------------------------------------------------------------------------
// Stable, persistent device id used by push registration so the same handset
// keeps the same row in `push_device_tokens` across app restarts.
// ---------------------------------------------------------------------------
export async function getOrCreateDeviceId(): Promise<string> {
  try {
    const existing = await SecureStore.getItemAsync(PUSH_DEVICE_ID_KEY);
    if (existing) return existing;
  } catch {
    // fall through to create
  }
  const fresh = `mob-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  try {
    await SecureStore.setItemAsync(PUSH_DEVICE_ID_KEY, fresh);
  } catch {
    // ignore — we still return a value so push registration can proceed
  }
  return fresh;
}

// Re-export the biometric pref key so the settings store / lock gate share it.
export const BIOMETRIC_PREF_STORAGE_KEY = BIOMETRIC_PREF_KEY;
