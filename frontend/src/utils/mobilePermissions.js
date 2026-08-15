const rolesFor = (user) => {
  const roles = new Set();
  if (user?.role) roles.add(String(user.role));
  if (Array.isArray(user?.roles)) {
    user.roles.forEach((role) => {
      if (role) roles.add(String(role));
    });
  }
  return roles;
};

const hasAnyRole = (user, allowedRoles) => {
  const roles = rolesFor(user);
  return allowedRoles.some((role) => roles.has(role));
};

export const canApproveMobileRequest = (user) => hasAnyRole(user, [
  'super_admin',
  'admin',
  'manager',
  'supervisor',
  'fnb_manager',
  'gm',
  'finance_manager',
]);

export const canAdjustMobileInventory = (user) => hasAnyRole(user, [
  'super_admin',
  'admin',
  'warehouse',
  'fnb_manager',
  'supervisor',
]);

export const canUpdateMobileOrderStatus = (user, status) => {
  if (hasAnyRole(user, ['super_admin', 'admin', 'fnb_supervisor', 'fnb_manager'])) {
    return ['pending', 'preparing', 'ready'].includes(status);
  }
  if (hasAnyRole(user, ['kitchen_staff'])) {
    return ['pending', 'preparing'].includes(status);
  }
  if (hasAnyRole(user, ['service'])) {
    return status === 'ready';
  }
  return false;
};
