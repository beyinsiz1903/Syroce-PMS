import {
  api,
  apiRequest,
  clearAllAuthStorage,
  getOrCreateDeviceId,
  getRefreshToken,
  setRefreshToken,
  setToken,
} from './client';

export type AuthUser = {
  id?: string;
  user_id?: string;
  tenant_id?: string;
  email?: string;
  username?: string;
  name?: string;
  role?: string;
  hotel_id?: string;
};

export type LoginResponse = {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  user: AuthUser;
  tenant?: Record<string, unknown>;
  challenge_token?: string;
  requires_2fa?: boolean;
};

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/login', { email, password });
  if (res?.access_token) {
    await setToken(res.access_token);
  }
  if (res?.refresh_token) {
    await setRefreshToken(res.refresh_token);
  } else {
    // Server didn't issue a refresh token (legacy deployment). Wipe any
    // stale refresh slot so we don't try to use a previous user's token.
    await setRefreshToken(null);
  }
  return res;
}

export async function logout(): Promise<void> {
  // V3 (round 7): unregister this device's push token FIRST so the
  // backend stops fanning notifications to a logged-out phone (privacy
  // + duplicate-delivery on next user). The unregister call needs the
  // current access token, so it has to run before /auth/logout revokes
  // it. Best-effort — failures here must not block logout.
  try {
    const deviceId = await getOrCreateDeviceId();
    await api.post('/api/notifications/push/unregister', { device_id: deviceId });
  } catch {
    // ignore — server may not support it, or device id missing
  }
  // V3: include the refresh token in the body so the backend revokes its
  // jti too. Without this, a stolen refresh token would remain usable
  // until natural expiry even after the user explicitly logs out.
  try {
    const stored = await getRefreshToken();
    await api.post('/api/auth/logout', stored ? { refresh_token: stored } : {});
  } catch {
    // ignore — server may already have rejected us
  }
  await clearAllAuthStorage();
}

export async function me(): Promise<AuthUser> {
  return api.get<AuthUser>('/api/auth/me');
}

export type RefreshResponse = {
  access_token: string;
  expires_in?: number;
  refresh_token?: string;
  token_type?: string;
};

export async function refreshAccessToken(): Promise<RefreshResponse> {
  // V3 — Syroce mobil refresh flow.
  // Preferred: send the long-lived refresh JWT in the body. The backend
  // validates it independently (does NOT require a valid Authorization
  // header), revokes its jti, mints a fresh access token + a brand-new
  // refresh token, and returns both. This means even after the access
  // token has expired (e.g. the app was backgrounded for hours) we can
  // still rotate cleanly without a re-login.
  //
  // Fallback: if no refresh token is stored (legacy install), we POST
  // without a body and the backend falls back to the old access-token
  // rotation path (still signed by an unexpired access token).
  const stored = await getRefreshToken();
  const res = await apiRequest<RefreshResponse>('/api/auth/refresh-token', {
    method: 'POST',
    body: stored ? { refresh_token: stored } : undefined,
    auth: !stored, // attach Authorization only on the legacy fallback path
  });
  if (res?.access_token) {
    await setToken(res.access_token);
    if (res.refresh_token) {
      await setRefreshToken(res.refresh_token);
    }
  }
  return res;
}

export async function registerPushDevice(payload: {
  device_id: string;
  push_token: string;
  platform: string;
  app_version?: string;
  os_version?: string;
  device_name?: string;
}): Promise<boolean> {
  // Returns true on success and false (instead of throwing) on backend
  // failure so the caller — `registerForPush()` — can update the
  // user-visible status indicator without crashing the post-login flow.
  // Push is a best-effort enhancement; the app stays usable either way.
  try {
    await api.post('/api/notifications/push/register', payload);
    return true;
  } catch {
    return false;
  }
}
