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
