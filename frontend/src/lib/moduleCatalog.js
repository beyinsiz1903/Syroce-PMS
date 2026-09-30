import { NAV_ITEMS } from '@/config/navItems';
import { MODULE_GROUPS, isModuleIncludedInPlan } from '@/pages/admin/tenantConstants';

const EXCLUDED_GROUPS = new Set([
  'pms_submodules', 'rms_submodules', 'channels_submodules',
  'reports_submodules', 'reports_items',
]);

const ROUTE_OVERRIDES = {
  pms: '/app/reservation-calendar',
  reservation_calendar: '/app/reservation-calendar',
  dashboard: '/app/dashboard',
  guests: '/app/pms?tab=guests',
  housekeeping: '/housekeeping',
  reports: '/app/raporlar',
  basic_reporting: '/app/raporlar',
  settings: '/app/settings',
  pms_mobile: '/mobile',
  invoices: '/app/invoices',
  invoices_basic: '/app/invoices',
  night_audit: '/night-audit',
  night_audit_basic: '/night-audit',
  channel_manager: '/channels',
  channel_manager_lite: '/channels',
  payments_link: '/app/invoices?tab=payments',
  kbs_notify: '/app/pms?tab=kbs',
  hr: '/app/hr',
  pos_fnb: '/pos',
  pos_basic: '/pos',
  parking: '/transfer-parking',
  maintenance: '/maintenance/work-orders',
  revenue_management: '/app/rms',
  multi_property: '/app/multi-property',
  group_sales: '/group-sales',
  sales_crm: '/sales-crm',
  loyalty_program: '/loyalty',
  audit_trail: '/audit-timeline',
  gm_dashboards: '/executive',
  spa: '/spa-wellness',
  mice: '/app/mice',
  academy: '/app/academy',
  contact_center: '/app/call-center',
  room_qr_requests: '/app/room-requests',
  quick_id: '/admin/quick-id',
  mailing: '/app/mailing',
  marketplace: '/app/marketplace',
  ai: '/app/ai',
  ai_chatbot: '/ai-chatbot',
  ai_pricing: '/dynamic-pricing',
  ai_predictive: '/predictive-analytics',
  ai_whatsapp: '/ai-whatsapp-concierge',
  ai_revenue_autopilot: '/revenue-autopilot',
  ai_social_radar: '/social-media-radar',
};

const navRouteFor = (key) => {
  if (ROUTE_OVERRIDES[key]) return ROUTE_OVERRIDES[key];
  const navItem = NAV_ITEMS.find((item) => item.key === key || item.moduleKey === key);
  return navItem?.path || null;
};

export const PRODUCT_MODULES = MODULE_GROUPS
  .filter((group) => !EXCLUDED_GROUPS.has(group.id))
  .flatMap((group) => group.items.map((item) => ({
    ...item,
    groupId: group.id,
    groupTitle: group.title,
    path: navRouteFor(item.key),
  })))
  .filter((item, index, rows) => rows.findIndex((row) => row.key === item.key) === index);

export function resolveModuleState(item, tenant = {}) {
  const modules = tenant.modules || {};
  const explicit = Object.prototype.hasOwnProperty.call(modules, item.key);
  const included = isModuleIncludedInPlan(item, tenant.subscription_tier || tenant.tier || 'basic');
  const enabled = explicit ? modules[item.key] === true : included;

  return {
    enabled,
    explicit,
    included,
    licensed: enabled || included,
    launchable: enabled && Boolean(item.path),
  };
}

export function moduleCounts(tenant = {}) {
  return PRODUCT_MODULES.reduce((result, item) => {
    const state = resolveModuleState(item, tenant);
    result.total += 1;
    if (state.enabled) result.enabled += 1;
    if (state.launchable) result.launchable += 1;
    if (state.enabled && !state.launchable) result.needsSetup += 1;
    return result;
  }, { total: 0, enabled: 0, launchable: 0, needsSetup: 0 });
}
