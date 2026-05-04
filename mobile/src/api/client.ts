import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'syroce.auth.token';

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
  } else {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  }
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

export async function apiRequest<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, opts.query);
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(opts.headers || {}),
  };
  if (opts.body && !isFormData(opts.body)) {
    headers['Content-Type'] = 'application/json';
  }
  if (opts.auth !== false) {
    const token = await getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (opts.body !== undefined && opts.body !== null) {
    body = isFormData(opts.body) ? opts.body : JSON.stringify(opts.body);
  }

  let res: Response;
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

  const text = await res.text();
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
  del: <T = unknown>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
};
