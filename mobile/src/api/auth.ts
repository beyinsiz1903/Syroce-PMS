import { api, setToken } from './client';

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
  return res;
}

export async function logout(): Promise<void> {
  try {
    await api.post('/api/auth/logout', {});
  } catch {
    // ignore
  }
  await setToken(null);
}

export async function me(): Promise<AuthUser> {
  return api.get<AuthUser>('/api/auth/me');
}

export async function registerPushDevice(payload: {
  device_id: string;
  push_token: string;
  platform: string;
  app_version?: string;
  os_version?: string;
}): Promise<void> {
  try {
    await api.post('/api/notifications/push/register', payload);
  } catch {
    // not critical for MVP
  }
}
