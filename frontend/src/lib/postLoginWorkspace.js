const ADMIN_ROLES = new Set([
  'super_admin',
  'platform_admin',
  'admin',
  'owner',
]);

export async function resolvePostLoginDestination({ api, user, tenant, existingRedirect = null }) {
  if (existingRedirect) return existingRedirect;

  const role = String(user?.role || '').toLowerCase();
  if (!user?.tenant_id) return null;
  if (!ADMIN_ROLES.has(role)) {
    // Missing entitlement data must not turn a role default into new access.
    if (!tenant?.modules) return null;
    const items = accessibleNavigationItems({ user, tenant, hasModule: key => tenant.modules[key] === true });
    return roleStartItems(user, items)[0]?.path || null;
  }

  try {
    const response = await api.get('/multi-property/properties');
    if ((response?.data?.properties || []).length > 1) {
      return '/app/multi-property';
    }
  } catch {
    // Standalone hotel admins have no central chain scope.
  }

  try {
    const response = await api.get('/onboarding/progress');
    const progress = response?.data || {};
    if (progress.dismissed === false && (progress.completed ?? 0) < 3) {
      return '/app/onboarding';
    }
  } catch {
    // Login remains successful even if an optional landing probe is unavailable.
  }

  return null;
}
import { accessibleNavigationItems } from '@/lib/navigationCatalog';
import { roleStartItems } from '@/lib/productExperience';
