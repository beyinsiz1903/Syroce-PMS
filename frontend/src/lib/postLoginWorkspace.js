const ADMIN_ROLES = new Set([
  'super_admin',
  'platform_admin',
  'admin',
  'owner',
]);

export async function resolvePostLoginDestination({ api, user, existingRedirect = null }) {
  if (existingRedirect) return existingRedirect;

  const role = String(user?.role || '').toLowerCase();
  if (!ADMIN_ROLES.has(role) || !user?.tenant_id) return null;

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
