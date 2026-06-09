import { create } from 'zustand';
import * as SecureStore from '../storage/secureStore';
import {
  AuthUser,
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
} from '../api/auth';
import { ApiError, clearAllAuthStorage, getToken } from '../api/client';

const USER_KEY = 'syroce.auth.user';

export type AppRole = 'front_desk' | 'housekeeping' | 'gm' | 'guest_app' | 'other';

function normalizeRole(raw: string | undefined): AppRole {
  if (!raw) return 'other';
  const r = raw.toLowerCase();
  if (['front_desk', 'reception', 'frontdesk', 'receptionist'].includes(r)) return 'front_desk';
  if (['housekeeping', 'housekeeper', 'hk'].includes(r)) return 'housekeeping';
  if (['gm', 'general_manager', 'manager', 'owner', 'super_admin', 'admin'].includes(r)) return 'gm';
  if (['guest', 'guest_app'].includes(r)) return 'guest_app';
  return 'other';
}

// All-access roles can browse EVERY role group's screens in the mobile app
// (not just their normalized home group). `normalizeRole` collapses these
// into 'gm', so we detect them from the RAW backend role to preserve the
// distinction. This is a UI-navigation affordance only — backend RBAC
// already grants super_admin/admin full authority; nothing is weakened here.
const ALL_ACCESS_ROLES = ['super_admin', 'admin'];

export function isAllAccessRole(raw: string | undefined): boolean {
  if (!raw) return false;
  return ALL_ACCESS_ROLES.includes(raw.toLowerCase());
}

export type AuthState = {
  user: AuthUser | null;
  role: AppRole;
  allAccess: boolean;
  loading: boolean;
  error: string | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

async function persistUser(user: AuthUser | null) {
  if (user) {
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user));
  } else {
    await SecureStore.deleteItemAsync(USER_KEY);
  }
}

async function readPersistedUser(): Promise<AuthUser | null> {
  try {
    const raw = await SecureStore.getItemAsync(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  role: 'other',
  allAccess: false,
  loading: true,
  error: null,

  async hydrate() {
    set({ loading: true, error: null });
    const token = await getToken();
    if (!token) {
      set({ user: null, role: 'other', allAccess: false, loading: false });
      return;
    }
    let user = await readPersistedUser();
    try {
      const fresh = await apiMe();
      if (fresh) {
        user = fresh;
        await persistUser(fresh);
      }
    } catch {
      // keep cached user — `apiMe` may have failed because we're offline
    }
    set({
      user,
      role: normalizeRole(user?.role),
      allAccess: isAllAccessRole(user?.role),
      loading: false,
    });
  },

  async login(email, password) {
    set({ loading: true, error: null });
    try {
      const res = await apiLogin(email, password);
      if (!res.access_token) {
        throw new Error('Geçersiz yanıt');
      }
      await persistUser(res.user);
      set({
        user: res.user,
        role: normalizeRole(res.user?.role),
        allAccess: isAllAccessRole(res.user?.role),
        loading: false,
        error: null,
      });
    } catch (e: unknown) {
      let msg: string;
      if (e instanceof ApiError) {
        msg =
          e.status === 401 || e.status === 400
            ? 'E-posta veya şifre hatalı'
            : e.status === 0
            ? 'Sunucuya ulaşılamıyor, tekrar dene'
            : e.message || 'Giriş başarısız';
      } else if (e instanceof Error) {
        msg = e.message;
      } else {
        msg = 'Giriş başarısız';
      }
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  async logout() {
    await apiLogout();
    await persistUser(null);
    // V3: wipe ALL credential / device-id storage so the next user starts
    // clean and a stolen handset cannot resume the previous session.
    await clearAllAuthStorage();
    set({ user: null, role: 'other', allAccess: false });
  },
}));
