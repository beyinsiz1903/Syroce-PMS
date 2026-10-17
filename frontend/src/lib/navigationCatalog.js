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
// Why a page is not in the menu, checked in this order (first failing rule
// wins). Module screens show the same reason next to the module, so "I
// enabled it but it is not in the menu" is answered where it is asked.
export const NAV_HIDDEN_REASONS = {
  staff_scope: 'Personelin yetki kapsamı dışında',
  hidden_item: 'Tesis menüsünde gizlenmiş',
  not_in_property_list: 'Tesis profilinin menü listesinde yok',
  hidden_group: 'Menü grubu gizlenmiş',
  platform_only: 'Yalnız platform yöneticisi',
  chain_only: 'Yalnız zincir otellerde',
  role: 'Kullanıcının rolü uygun değil',
  not_in_plan: 'Pakette yok',
  module_disabled: 'Yönetici modülü kapattı',
  module_off: 'Modül kapalı',
};

function navigationContext({ user, tenant, isSuperAdmin = false, hasModule = () => true, moduleOffReason }) {
  return {
    user,
    tenant,
    isSuperAdmin,
    hasModule,
    moduleOffReason: moduleOffReason || (() => 'module_off'),
    hiddenGroups: new Set(tenant?.hidden_nav_groups || []),
    hiddenItems: new Set(tenant?.hidden_nav_items || []),
    visibleItems: new Set(tenant?.visible_nav_items || []),
    userRoles: new Set([
      user?.role,
      ...(Array.isArray(user?.roles) ? user.roles : []),
    ].filter(Boolean).map((role) => String(role).trim().toLowerCase())),
  };
}

function hiddenReason(item, ctx) {
  if (!canAccessNavItem(ctx.user, item)) return 'staff_scope';
  // Property-level navigation choices describe the hotel's workspace and
  // must be honoured for administrators too. Platform-only entries remain
  // available through their explicit super-admin routes.
  if (ctx.hiddenItems.has(item.key)) return 'hidden_item';
  if (ctx.visibleItems.size > 0 && !ctx.visibleItems.has(item.key)) return 'not_in_property_list';
  if (item.navGroup && ctx.hiddenGroups.has(item.navGroup)) return 'hidden_group';
  if (item.requireSuperAdmin && !ctx.isSuperAdmin) return 'platform_only';
  if (item.requireChain && !ctx.tenant?.chain_id) return 'chain_only';
  if (
    Array.isArray(item.allowedRoles)
    && !ctx.isSuperAdmin
    && !item.allowedRoles.some((role) => ctx.userRoles.has(String(role).trim().toLowerCase()))
  ) return 'role';
  if (Array.isArray(item.anyModuleKeys) && item.anyModuleKeys.length) {
    if (!item.anyModuleKeys.some((key) => ctx.hasModule(key))) return ctx.moduleOffReason(item.anyModuleKeys[0]);
  } else if (item.moduleKey && !(ctx.isSuperAdmin && item.requireSuperAdmin) && !ctx.hasModule(item.moduleKey)) {
    return ctx.moduleOffReason(item.moduleKey);
  }
  return null;
}

/** One menu decision with its reason: { visible, reason, reasonLabel }. */
export function explainNavigationItem(item, options) {
  const reason = hiddenReason(item, navigationContext(options));
  return { visible: !reason, reason, reasonLabel: reason ? NAV_HIDDEN_REASONS[reason] || reason : null };
}

/** Menu pages a module opens (direct or shared), each with its decision. */
export function moduleNavigationStatus(moduleKey, options) {
  const ctx = navigationContext(options);
  return NAV_ITEMS
    .filter((item) => item.moduleKey === moduleKey || (item.anyModuleKeys || []).includes(moduleKey))
    .filter((item) => !item.requireSuperAdmin)
    .map((item) => {
      const reason = hiddenReason(item, ctx);
      return { key: item.key, label: item.label, path: item.path, visible: !reason, reason, reasonLabel: reason ? NAV_HIDDEN_REASONS[reason] || reason : null };
    });
}

export function accessibleNavigationItems(options) {
  const ctx = navigationContext(options);
  const itemLabels = options?.tenant?.nav_item_labels || {};
  return [...NAV_ITEMS, ...supplementalModuleNavItems(options?.user)]
    .filter((item) => !hiddenReason(item, ctx))
    .map((item) => itemLabels[item.key] ? { ...item, label: itemLabels[item.key] } : item);
}

export function navigationItemsByGroup(items) {
  return items.reduce((groups, item) => {
    if (!item.navGroup) return groups;
    (groups[item.navGroup] ||= []).push(item);
    return groups;
  }, {});
}
