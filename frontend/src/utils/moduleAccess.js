// Canonical top-level module access helper.
//
// Explicit `module_scopes` is authoritative. When the field is absent we use
// conservative role defaults for backwards compatibility. An explicit empty
// array means the user has no module access.

export const MODULE_SCOPES = Object.freeze([
  'cashier',
  'channel_manager',
  'finance',
  'frontdesk',
  'housekeeping',
  'hr',
  'invoice',
  'maintenance',
  'pos',
  'procurement',
  'reports',
  'sales',
  'stock',
  'tasks',
]);

const MODULE_SCOPE_SET = new Set(MODULE_SCOPES);

const ROLE_DEFAULT_MODULE_SCOPES = Object.freeze({
  admin: MODULE_SCOPES,
  supervisor: MODULE_SCOPES,
  front_desk: ['frontdesk'],
  housekeeping: ['housekeeping', 'tasks'],
  sales: ['sales', 'reports'],
  finance: ['cashier', 'finance', 'invoice', 'reports'],
  procurement: ['procurement', 'stock'],
  staff: [],
});

export function normalizeModuleScope(scope) {
  if (typeof scope !== 'string') return null;
  let normalized = scope.trim().toLowerCase().replaceAll('-', '_');
  if (normalized.endsWith('.*')) normalized = normalized.slice(0, -2);
  if (normalized === '*') return normalized;
  return MODULE_SCOPE_SET.has(normalized) ? normalized : null;
}

export function effectiveModuleScopes(user) {
  if (!user) return [];
  const role = typeof user.role === 'string' ? user.role : user.role?.value;
  if (role === 'super_admin') return ['*'];

  if (Object.prototype.hasOwnProperty.call(user, 'module_scopes')) {
    if (!Array.isArray(user.module_scopes)) return [];
    return [...new Set(user.module_scopes.map(normalizeModuleScope).filter(Boolean))];
  }

  return ROLE_DEFAULT_MODULE_SCOPES[role] || [];
}

export function hasModuleAccess(user, scope) {
  const normalized = normalizeModuleScope(scope);
  if (!normalized) return false;
  const granted = effectiveModuleScopes(user);
  return granted.includes('*') || granted.includes(normalized);
}
