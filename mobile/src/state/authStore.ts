import { create } from 'zustand';
import * as SecureStore from '../storage/secureStore';
import {
  AuthUser,
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
  verifyTwoFactor as apiVerifyTwoFactor,
} from '../api/auth';
import { ApiError, clearAllAuthStorage, getToken } from '../api/client';
import { clearOfflineCache } from '../cache/persister';
import { queryClient } from '../cache/queryClient';
import { tr } from '../i18n/tr';
import { deriveMobileAccess } from './roleAccess';
import { beginAuthSession, currentAuthSession, expireAuthSession, isCurrentAuthSession, onAuthSessionExpired, writeForAuthSession } from './authSession';

// The pure role/entitlement helpers live in `roleAccess.ts` (no React/RN/
// zustand imports) so the plain-Node unit test runner can exercise them. They
// are re-exported here so existing `state/authStore` import sites keep working.
export type { AppRole } from './roleAccess';
export {
  canViewFinanceReports,
  hasApprovalsAccess,
  hasDepartmentAccess,
  hasHrAccess,
  hasMaintenanceAccess,
  hasMiceAccess,
  hasPosAccess,
  hasProcurementAccess,
  hasRevenueAccess,
  hasSpaAccess,
  isAllAccessRole,
  normalizeRole,
} from './roleAccess';

const USER_KEY = 'syroce.auth.user';

export type AuthState = ReturnType<typeof deriveMobileAccess> & {
  user: AuthUser | null;
  pendingTwoFactorToken: string | null;
  allAccess: boolean;
  financeReports: boolean;
  spaAccess: boolean;
  miceAccess: boolean;
  maintenanceAccess: boolean;
  procurementAccess: boolean;
  hrAccess: boolean;
  revenueAccess: boolean;
  posAccess: boolean;
  deptAccess: boolean;
  approvalsAccess: boolean;
  loading: boolean;
  error: string | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  verifyTwoFactor: (code: string) => Promise<void>;
  cancelTwoFactor: () => void;
  logout: () => Promise<void>;
};

async function persistUser(user: AuthUser, revision: number) {
  await writeForAuthSession(revision, () => SecureStore.setItemAsync(USER_KEY, JSON.stringify(user)));
}

async function clearLocalSession(revision: number) {
  await writeForAuthSession(revision, async () => {
    await queryClient.cancelQueries();
    queryClient.clear();
    await clearOfflineCache();
    await SecureStore.deleteItemAsync(USER_KEY);
    await clearAllAuthStorage();
  });
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
  ...deriveMobileAccess(null),
  user: null,
  pendingTwoFactorToken: null,
  role: 'other',
  allAccess: false,
  financeReports: false,
  spaAccess: false,
  miceAccess: false,
  maintenanceAccess: false,
  procurementAccess: false,
  hrAccess: false,
  revenueAccess: false,
  posAccess: false,
  deptAccess: false,
  approvalsAccess: false,
  loading: true,
  error: null,

  async hydrate() {
    const revision = currentAuthSession();
    set({ loading: true, error: null });
    const token = await getToken();
    if (!isCurrentAuthSession(revision)) return;
    if (!token) {
      await clearLocalSession(revision);
      if (!isCurrentAuthSession(revision)) return;
      set({
        ...deriveMobileAccess(null),
        user: null,
        role: 'other',
        allAccess: false,
        financeReports: false,
        spaAccess: false,
        miceAccess: false,
        maintenanceAccess: false,
        procurementAccess: false,
        hrAccess: false,
        revenueAccess: false,
        posAccess: false,
        deptAccess: false,
        approvalsAccess: false,
        loading: false,
      });
      return;
    }
    let user = await readPersistedUser();
    try {
      const fresh = await apiMe();
      if (!isCurrentAuthSession(revision)) return;
      if (fresh) {
        if (JSON.stringify(user) !== JSON.stringify(fresh)) {
          await queryClient.cancelQueries();
          queryClient.clear();
          await clearOfflineCache();
        }
        user = fresh;
        await persistUser(fresh, revision);
      }
    } catch (e: unknown) {
      if (!isCurrentAuthSession(revision)) return;
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        // Refresh already had one chance in the API interceptor. A remaining
        // 401 means the session was revoked/expired; do not expose a stale
        // cached identity or leave the app in a failing request loop.
        await expireAuthSession(revision);
        return;
      }
      // Network/5xx failures keep the cached user so an already-authenticated
      // operator can continue using the offline-capable surfaces.
    }
    if (!isCurrentAuthSession(revision)) return;
    set({
      user,
      ...deriveMobileAccess(user),
      loading: false,
    });
  },

  async login(email, password) {
    const revision = beginAuthSession();
    set({
      ...deriveMobileAccess(null),
      loading: true,
      error: null,
      user: null,
      pendingTwoFactorToken: null,
      role: 'other',
      allAccess: false,
      financeReports: false,
      spaAccess: false,
      miceAccess: false,
      maintenanceAccess: false,
      procurementAccess: false,
      hrAccess: false,
      revenueAccess: false,
      posAccess: false,
      deptAccess: false,
      approvalsAccess: false,
    });
    try {
      // A fresh credential attempt starts with no previous account data in
      // memory or on disk. Per-account POS queues are kept separately.
      await clearLocalSession(revision);
      if (!isCurrentAuthSession(revision)) return;
      const res = await apiLogin(email, password);
      if (!isCurrentAuthSession(revision)) return;
      if (res.requires_2fa && res.challenge_token) {
        set({ loading: false, pendingTwoFactorToken: res.challenge_token, error: null });
        return;
      }
      if (!res.access_token) {
        throw new Error('Geçersiz yanıt');
      }
      await persistUser(res.user, revision);
      if (!isCurrentAuthSession(revision)) return;
      set({
        user: res.user,
        pendingTwoFactorToken: null,
        ...deriveMobileAccess(res.user),
        loading: false,
        error: null,
      });
    } catch (e: unknown) {
      if (!isCurrentAuthSession(revision)) return;
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
      await clearLocalSession(revision);
      if (!isCurrentAuthSession(revision)) return;
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  async verifyTwoFactor(code) {
    const revision = currentAuthSession();
    const challengeToken = useAuthStore.getState().pendingTwoFactorToken;
    if (!challengeToken) throw new Error('Giriş doğrulamasını yeniden başlatın');
    set({ loading: true, error: null });
    try {
      const res = await apiVerifyTwoFactor(challengeToken, code);
      if (!isCurrentAuthSession(revision)) return;
      if (!res.access_token || !res.user) throw new Error('İki aşamalı doğrulama yanıtı geçersiz');
      await persistUser(res.user, revision);
      if (!isCurrentAuthSession(revision)) return;
      set({
        user: res.user,
        pendingTwoFactorToken: null,
        ...deriveMobileAccess(res.user),
        loading: false,
        error: null,
      });
    } catch (e: unknown) {
      if (!isCurrentAuthSession(revision)) return;
      // Backend challenges are single-use. A rejected code needs a new
      // password login before another verification attempt can be made.
      await clearLocalSession(revision);
      if (!isCurrentAuthSession(revision)) return;
      set({ loading: false, pendingTwoFactorToken: null, error: tr.auth.twoFactorInvalid });
      throw e;
    }
  },

  cancelTwoFactor() {
    // A late accepted code from a cancelled challenge cannot sign back in.
    const revision = beginAuthSession();
    set({ pendingTwoFactorToken: null, error: null, loading: true });
    void clearLocalSession(revision).finally(() => {
      if (isCurrentAuthSession(revision)) set({ loading: false });
    });
  },

  async logout() {
    const revision = beginAuthSession();
    set({
      ...deriveMobileAccess(null),
      user: null,
      pendingTwoFactorToken: null,
      role: 'other',
      allAccess: false,
      financeReports: false,
      spaAccess: false,
      miceAccess: false,
      maintenanceAccess: false,
      procurementAccess: false,
      hrAccess: false,
      revenueAccess: false,
      posAccess: false,
      deptAccess: false,
      approvalsAccess: false,
      loading: true,
    });
    try { await apiLogout(); }
    finally {
      await clearLocalSession(revision);
      if (isCurrentAuthSession(revision)) set({ loading: false, error: null });
    }
  },
}));

onAuthSessionExpired(async revision => {
  useAuthStore.setState({ ...deriveMobileAccess(null), user: null, pendingTwoFactorToken: null, loading: true });
  try { await clearLocalSession(revision); }
  finally {
    if (isCurrentAuthSession(revision)) useAuthStore.setState({ loading: false, error: 'Oturumunuz sona erdi. Lütfen yeniden giriş yapın.' });
  }
});
