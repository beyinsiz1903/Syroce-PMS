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
  guest_advanced: '/app/pms?tab=guests',
  housekeeping: '/housekeeping',
  housekeeping_advanced: '/housekeeping',
  reports: '/app/raporlar',
  basic_reporting: '/app/raporlar',
  settings: '/app/settings',
  pms_mobile: '/mobile',
  invoices: '/app/invoices',
  invoices_basic: '/app/invoices',
  folio_basic: '/app/pms?tab=cashier',
  folio_management: '/app/folio-management',
  cost_management: '/app/cost-management',
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
  rate_management: '/unified-rate-manager',
  booking_engine: '/app/wbe-settings',
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
  ai_reputation: '/app/ai?module=reputation-manager',
  api_access: '/app/integration-hub',
  white_label: '/app/settings',
  operator_incident: '/operational-events',
  lockdown: '/security',
  mobile_housekeeping: '/mobile/housekeeping',
  mobile_revenue: '/mobile/revenue',
};

const INTEGRATION_REQUIRED_MODULES = new Set([
  'channel_manager', 'channel_manager_lite', 'payments_link', 'kbs_notify',
  'booking_engine', 'invoices', 'quick_id', 'af_sadakat', 'api_access',
  'ai_whatsapp',
]);

const MODULE_USAGE_EVENTS = {
  pms: ['reservation_created', 'reservation_cancelled'],
  reservation_calendar: ['reservation_created', 'reservation_cancelled'],
  guests: ['guest_created'],
  guest_advanced: ['guest_created'],
  reports: ['report_generated'],
  basic_reporting: ['report_generated'],
  invoices: ['invoice_created'],
  invoices_basic: ['invoice_created'],
  night_audit: ['night_audit_run'],
  night_audit_basic: ['night_audit_run'],
  channel_manager: ['channel_sync', 'webhook_received'],
  channel_manager_lite: ['channel_sync', 'webhook_received'],
  ai: ['ai_request'],
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
    path: item.path || null,
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

export function moduleIntegrationLabel(item, state) {
  if (!INTEGRATION_REQUIRED_MODULES.has(item.key)) return 'Entegrasyon gerektirmiyor';
  if (!state.enabled) return 'Erişim kapalı';
  return 'Sağlık verisi bekleniyor';
}

export function moduleUsageLabel(item, usage = {}) {
  const events = usage.events || {};
  const eventKeys = MODULE_USAGE_EVENTS[item.key] || [];
  if (!eventKeys.length) return 'Modül bazlı ölçüm yok';
  const total = eventKeys.reduce((sum, key) => sum + Number(events[key] || 0), 0);
  return total > 0 ? `Son ${usage.period_days || 30} günde ${total} işlem` : 'Son dönemde kullanım yok';
}
