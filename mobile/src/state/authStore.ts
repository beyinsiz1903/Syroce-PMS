import { create } from 'zustand';
import * as SecureStore from '../storage/secureStore';
import {
  AuthUser,
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
  verifyTwoFactor as apiVerifyTwoFactor,
} from '../api/auth';
import { ApiError, clearAllAuthStorage, getToken, setRefreshToken, setToken } from '../api/client';
import { clearOfflineCache } from '../cache/persister';
import { queryClient } from '../cache/queryClient';
import { tr } from '../i18n/tr';
import type { AppRole } from './roleAccess';
import {
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
  hasServerAccess,
} from './roleAccess';

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

export type AuthState = {
  user: AuthUser | null;
  pendingTwoFactorToken: string | null;
  role: AppRole;
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
    set({ loading: true, error: null });
    const token = await getToken();
    if (!token) {
      queryClient.clear();
      await clearOfflineCache();
      set({
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
      if (fresh) {
        user = fresh;
        await persistUser(fresh);
      }
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 401) {
        // Refresh already had one chance in the API interceptor. A remaining
        // 401 means the session was revoked/expired; do not expose a stale
        // cached identity or leave the app in a failing request loop.
        await persistUser(null);
        await clearAllAuthStorage();
        queryClient.clear();
        await clearOfflineCache();
        user = null;
      }
      // Network/5xx failures keep the cached user so an already-authenticated
      // operator can continue using the offline-capable surfaces.
    }
    const server = (page: string, permission: string, fallback: boolean) => hasServerAccess(user || undefined, page, permission) ?? fallback;
    set({
      user,
      role: normalizeRole(user?.role),
      allAccess: isAllAccessRole(user?.role),
      financeReports: server('finance', 'view_finance_reports', canViewFinanceReports(user?.role)),
      spaAccess: hasSpaAccess(user?.role),
      miceAccess: hasMiceAccess(user?.role),
      maintenanceAccess: server('maintenance', 'view_maintenance', hasMaintenanceAccess(user?.role)),
      procurementAccess: hasProcurementAccess(user?.role),
      hrAccess: hasHrAccess(user?.role),
      revenueAccess: hasRevenueAccess(user?.role),
      posAccess: hasPosAccess(user?.role),
      deptAccess: server('departments', 'view_departments', hasDepartmentAccess(user?.role)),
      approvalsAccess: hasApprovalsAccess(user?.role),
      loading: false,
    });
  },

  async login(email, password) {
    set({
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
      queryClient.clear();
      await clearOfflineCache();
      await setToken(null);
      await setRefreshToken(null);
      await persistUser(null);
      const res = await apiLogin(email, password);
      if (res.requires_2fa && res.challenge_token) {
        await setToken(null);
        set({ loading: false, pendingTwoFactorToken: res.challenge_token, error: null });
        return;
      }
      if (!res.access_token) {
        throw new Error('Geçersiz yanıt');
      }
      await persistUser(res.user);
      const server = (page: string, permission: string, fallback: boolean) => hasServerAccess(res.user, page, permission) ?? fallback;
      set({
        user: res.user,
        pendingTwoFactorToken: null,
        role: normalizeRole(res.user?.role),
        allAccess: isAllAccessRole(res.user?.role),
        financeReports: server('finance', 'view_finance_reports', canViewFinanceReports(res.user?.role)),
        spaAccess: hasSpaAccess(res.user?.role),
        miceAccess: hasMiceAccess(res.user?.role),
        maintenanceAccess: server('maintenance', 'view_maintenance', hasMaintenanceAccess(res.user?.role)),
        procurementAccess: hasProcurementAccess(res.user?.role),
        hrAccess: hasHrAccess(res.user?.role),
        revenueAccess: hasRevenueAccess(res.user?.role),
        posAccess: hasPosAccess(res.user?.role),
        deptAccess: server('departments', 'view_departments', hasDepartmentAccess(res.user?.role)),
        approvalsAccess: hasApprovalsAccess(res.user?.role),
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

  async verifyTwoFactor(code) {
    const challengeToken = useAuthStore.getState().pendingTwoFactorToken;
    if (!challengeToken) throw new Error('Giriş doğrulamasını yeniden başlatın');
    set({ loading: true, error: null });
    try {
      const res = await apiVerifyTwoFactor(challengeToken, code);
      if (!res.access_token || !res.user) throw new Error('İki aşamalı doğrulama yanıtı geçersiz');
      await persistUser(res.user);
      set({
        user: res.user,
        pendingTwoFactorToken: null,
        role: normalizeRole(res.user.role),
        allAccess: isAllAccessRole(res.user.role),
        financeReports: canViewFinanceReports(res.user.role),
        spaAccess: hasSpaAccess(res.user.role),
        miceAccess: hasMiceAccess(res.user.role),
        maintenanceAccess: hasMaintenanceAccess(res.user.role),
        procurementAccess: hasProcurementAccess(res.user.role),
        hrAccess: hasHrAccess(res.user.role),
        revenueAccess: hasRevenueAccess(res.user.role),
        posAccess: hasPosAccess(res.user.role),
        deptAccess: hasDepartmentAccess(res.user.role),
        approvalsAccess: hasApprovalsAccess(res.user.role),
        loading: false,
        error: null,
      });
    } catch (e: unknown) {
      // Backend challenges are single-use. A rejected code needs a new
      // password login before another verification attempt can be made.
      await setToken(null);
      await setRefreshToken(null);
      await persistUser(null);
      set({ loading: false, pendingTwoFactorToken: null, error: tr.auth.twoFactorInvalid });
      throw e;
    }
  },

  cancelTwoFactor() {
    set({ pendingTwoFactorToken: null, error: null });
  },

  async logout() {
    await apiLogout();
    await persistUser(null);
    // V3: wipe ALL credential / device-id storage so the next user starts
    // clean and a stolen handset cannot resume the previous session.
    await clearAllAuthStorage();
    queryClient.clear();
    await clearOfflineCache();
    set({
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
  },
}));
