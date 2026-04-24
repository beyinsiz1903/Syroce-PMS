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
