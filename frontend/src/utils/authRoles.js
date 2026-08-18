export function isSuperAdmin(user) {
  if (!user) return false;
  if (user.role === 'super_admin') return true;
  if (Array.isArray(user.roles) && user.roles.includes('super_admin')) return true;
  return false;
}

export function hasRole(user, ...allowedRoles) {
  if (!user) return false;
  if (isSuperAdmin(user)) return true;
  if (allowedRoles.includes(user.role)) return true;
  if (Array.isArray(user.roles) && user.roles.some((r) => allowedRoles.includes(r))) return true;
  return false;
}

// Task #28: Kullanıcıya tek tek verilmiş operasyon-seviyesi izinler
// (`granted_permissions`) backend'de RBAC'in üstüne eklenir. Frontend
// karar noktaları (örn. "Acil mesaj seçeneği görünür mü?") aynı çift
// kontrolü yapar.
export function hasGrantedPermission(user, permission) {
  if (!user || !permission) return false;
  const granted = user.granted_permissions;
  if (!Array.isArray(granted)) return false;
  return granted.includes(permission);
}

export function canSendUrgentMessage(user) {
  return hasRole(user, 'admin', 'supervisor')
    || hasGrantedPermission(user, 'send_urgent_message');
}

function normalizeModuleScope(value) {
  if (typeof value !== 'string') return '';
  return value.trim().toLowerCase().replaceAll('-', '_');
}

// Opt-in least-privilege module allowlist. Legacy users without a scope list
// keep the existing role/tenant behaviour. Once a non-empty list is present,
// direct route access becomes fail-closed. `*` and `prefix.*` are supported.
export function hasModuleScope(user, moduleKey) {
  if (isSuperAdmin(user)) return true;

  const rawScopes = user?.module_scopes;
  if (!Array.isArray(rawScopes) || rawScopes.length === 0) return true;

  const requested = normalizeModuleScope(moduleKey);
  if (!requested) return false;

  const scopes = new Set(rawScopes.map(normalizeModuleScope).filter(Boolean));
  if (scopes.has('*') || scopes.has(requested)) return true;

  for (const scope of scopes) {
    if (!scope.endsWith('.*')) continue;
    const prefix = scope.slice(0, -2);
    if (
      requested === prefix
      || requested.startsWith(`${prefix}.`)
      || requested.startsWith(`${prefix}_`)
    ) {
      return true;
    }
  }
  return false;
}
