import axios from 'axios';

export const ADMIN_TENANT_CONTEXT_KEY = 'admin_tenant_context';

function safeParse(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function notifyAuthChanged() {
  try {
    if (navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'AUTH_CHANGED' });
    }
  } catch {
    // Service workers are optional; session isolation is still enforced by
    // the server and the full-page navigation below.
  }
}

function clearTenantCaches() {
  localStorage.removeItem('entitlements');
  try {
    sessionStorage.removeItem('notif_cache_v1');
    sessionStorage.removeItem('pms_bd_cache_v1');
  } catch {
    // Storage can be unavailable in hardened/private browser modes.
  }
  notifyAuthChanged();
}

function persistSession({ user, tenant, modules, accessToken }) {
  localStorage.setItem('user', JSON.stringify(user));
  localStorage.setItem('tenant', JSON.stringify(tenant));
  localStorage.setItem('modules', JSON.stringify(modules || tenant?.modules || {}));
  localStorage.setItem('token_ts', String(Date.now()));

  if (accessToken) {
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
    if (window.navigator.webdriver || import.meta.env.DEV) {
      localStorage.setItem('token', accessToken);
    }
  }
  clearTenantCaches();
}

export function persistEnteredTenantContext(payload) {
  if (!payload?.user || !payload?.tenant || !payload?.origin) {
    throw new Error('Eksik otel çalışma bağlamı yanıtı');
  }
  localStorage.setItem(
    ADMIN_TENANT_CONTEXT_KEY,
    JSON.stringify({
      origin: payload.origin,
      target: {
        user: payload.user,
        tenant: payload.tenant,
        modules: payload.modules || payload.tenant.modules || {},
      },
      expires_at: payload.expires_at || null,
    }),
  );
  persistSession({
    user: payload.user,
    tenant: payload.tenant,
    modules: payload.modules,
    accessToken: payload.access_token,
  });
}

export function persistExitedTenantContext(payload) {
  if (!payload?.user || !payload?.tenant) {
    throw new Error('Eksik süperadmin oturum yanıtı');
  }
  localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
  persistSession({
    user: payload.user,
    tenant: payload.tenant,
    modules: payload.modules,
    accessToken: payload.access_token,
  });
}

export function readAdminTenantContext() {
  return safeParse(localStorage.getItem(ADMIN_TENANT_CONTEXT_KEY));
}

export function isAdminTenantContextActive() {
  const user = safeParse(localStorage.getItem('user'));
  return Boolean(user?.is_impersonating && readAdminTenantContext()?.origin);
}

export function restoreOriginTenantContext(freshUser = null) {
  const context = readAdminTenantContext();
  const origin = context?.origin;
  if (!origin?.user || !origin?.tenant) return false;
  if (freshUser?.id && origin.user.id !== freshUser.id) return false;

  localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
  persistSession({
    user: freshUser || origin.user,
    tenant: origin.tenant,
    modules: origin.modules,
  });
  return true;
}

export function reconcileAdminTenantContext(freshUser, tenant, modules) {
  const context = readAdminTenantContext();
  if (!context) return { user: freshUser, tenant, modules };

  if (freshUser?.is_impersonating) {
    const target = context.target;
    if (target?.tenant?.id === freshUser.tenant_id) {
      return {
        user: freshUser,
        tenant: target.tenant,
        modules: target.modules || target.tenant.modules || {},
      };
    }
    return { user: freshUser, tenant, modules };
  }

  const origin = context.origin;
  if (origin?.user?.id === freshUser?.id && origin?.tenant?.id === freshUser?.tenant_id) {
    localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
    return {
      user: freshUser,
      tenant: origin.tenant,
      modules: origin.modules || origin.tenant.modules || {},
    };
  }

  localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
  return { user: freshUser, tenant, modules };
}
