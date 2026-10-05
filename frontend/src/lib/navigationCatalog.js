import { NAV_ITEMS } from '@/config/navItems';
import {
  canAccessNavItem,
  supplementalModuleNavItems,
} from '@/utils/moduleAccess';

/**
 * Otel kabuğu ile Uygulama Merkezi'nin kullandığı tek navigasyon kaynağı.
 * Yetki, lisans, tesis görünürlüğü ve zincir kapsamı burada birlikte uygulanır;
 * böylece bir kullanıcı üst menüde farklı, uygulama merkezinde farklı bir liste
 * görmez.
 */
export function accessibleNavigationItems({
  user,
  tenant,
  isSuperAdmin = false,
  hasModule = () => true,
}) {
  const hiddenGroups = new Set(tenant?.hidden_nav_groups || []);
  const hiddenItems = new Set(tenant?.hidden_nav_items || []);
  const userRoles = new Set([
    user?.role,
    ...(Array.isArray(user?.roles) ? user.roles : []),
  ].filter(Boolean).map((role) => String(role).trim().toLowerCase()));

  return [...NAV_ITEMS, ...supplementalModuleNavItems(user)].filter((item) => {
    if (!canAccessNavItem(user, item)) return false;
    // Property-level navigation choices describe the hotel's workspace and
    // must be honoured for administrators too. Platform-only entries remain
    // available through their explicit super-admin routes.
    if (hiddenItems.has(item.key)) return false;
    if (item.navGroup && hiddenGroups.has(item.navGroup)) return false;
    if (item.requireSuperAdmin && !isSuperAdmin) return false;
    if (item.requireChain && !tenant?.chain_id) return false;
    if (
      Array.isArray(item.allowedRoles)
      && !isSuperAdmin
      && !item.allowedRoles.some((role) => userRoles.has(String(role).trim().toLowerCase()))
    ) return false;
    if (item.moduleKey && !(isSuperAdmin && item.requireSuperAdmin) && !hasModule(item.moduleKey)) return false;
    return true;
  });
}

export function navigationItemsByGroup(items) {
  return items.reduce((groups, item) => {
    if (!item.navGroup) return groups;
    (groups[item.navGroup] ||= []).push(item);
    return groups;
  }, {});
}
