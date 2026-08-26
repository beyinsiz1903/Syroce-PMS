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
const LEGACY_UNSCOPED_SURFACE = '__legacy_unscoped_surface__';

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

const COMMON_ROUTE_PATHS = new Set([
  '/app/dashboard',
  '/dashboard-simple',
  '/app/profile',
  '/profile',
]);

const COMMON_NAV_KEYS = new Set(['dashboard']);

const EXACT_ROUTE_SCOPES = Object.freeze({
  '/app/pms': ['frontdesk'],
  '/pms': ['frontdesk'],
  '/pms-operations': ['frontdesk'],
  '/app/reservation-calendar': ['frontdesk'],
  '/reservation-calendar': ['frontdesk'],
  '/walkin': ['frontdesk'],
  '/room-map': ['frontdesk'],
  '/frontdesk/audit-checklist': ['frontdesk'],
  '/shift-handover': ['frontdesk'],
  '/settings/early-late-pricing': ['frontdesk'],
  '/eod-report': ['frontdesk'],
  '/wake-up-calls': ['frontdesk'],
  '/departure-list': ['frontdesk'],
  '/no-show-today': ['frontdesk'],
  '/transfer-parking': ['frontdesk'],
  '/guest-journey': ['frontdesk'],

  '/housekeeping': ['housekeeping'],
  '/housekeeping-status': ['housekeeping'],
  '/lost-found': ['housekeeping'],

  '/app/cashier': ['cashier'],
  '/folio-detail': ['cashier'],
  '/group-folio': ['cashier'],

  '/invoices': ['invoice'],
  '/app/invoices': ['invoice'],
  '/efatura': ['invoice'],
  '/app/konaklama-vergisi': ['invoice'],

  '/app/general-ledger': ['finance'],
  '/app/bank-reconciliation': ['finance'],
  '/app/fnb-costing': ['finance'],
  '/pending-ar': ['finance'],
  '/city-ledger': ['finance'],

  '/app/procurement': ['procurement'],
  '/app/supplies-market': ['procurement'],
  '/app/stock-rehber': ['stock', 'procurement'],
  '/hotel-inventory': ['stock'],
  '/hotel-inventory/transfers': ['stock'],

  '/sales': ['sales'],
  '/group-sales': ['sales'],
  '/sales-crm': ['sales'],
  '/group-bookings-manage': ['sales'],
  '/block-management': ['sales'],
  '/deposit-tracking': ['sales'],
  '/service-recovery': ['sales'],

  '/hr': ['hr'],
  '/app/hr': ['hr'],
  '/hr/shifts': ['hr'],
  '/staff-management': ['hr'],

  '/reports': ['reports'],
  '/app/reports': ['reports'],
  '/app/raporlar': ['reports'],
  '/app/gelismis-raporlar': ['reports'],
  '/reports/builder': ['reports'],
  '/app/rapor-olusturucu': ['reports'],
  '/reports/official-guest-list': ['reports'],
  '/reports/corporate-contracts': ['reports'],
  '/reports/corporate-contract-approvals': ['reports'],
  '/report-scheduler': ['reports'],
  '/audit-timeline': ['reports'],
  '/urgent-message-report': ['reports'],
  '/recalled-messages-report': ['reports'],
  '/id-photo-view-report': ['reports'],
  '/no-show-analytics': ['reports'],
  '/app/sustainability': ['reports'],
  '/app/migration-observability': ['reports'],
  '/app/mevzuat-raporlari': ['reports'],

  '/channel-manager': ['channel_manager'],
  '/app/channel-manager': ['channel_manager'],
  '/channels': ['channel_manager'],
  '/app/channels': ['channel_manager'],
  '/cm-dashboard': ['channel_manager'],
  '/go-live-readiness': ['channel_manager'],
  '/mapping-manager': ['channel_manager'],
  '/room-mapping-wizard': ['channel_manager'],
  '/unified-rate-manager': ['channel_manager'],
  '/channel-connections': ['channel_manager'],
  '/channel-ops': ['channel_manager'],
  '/wire-failures': ['channel_manager'],
  '/ari-push': ['channel_manager'],
  '/travel-agent-arap': ['channel_manager'],
  '/agency-management': ['channel_manager'],
  '/app/incoming-agency-contracts': ['channel_manager'],
  '/agency-content': ['channel_manager'],
  '/b2b-analytics': ['channel_manager'],
  '/app/integration-hub': ['channel_manager', 'invoice'],

  '/pos': ['pos'],
  '/pos/terminal': ['pos'],
  '/pos-extensions': ['pos'],
  '/staff/room-service': ['pos'],
  '/minibar': ['pos'],

  '/app/tasks': ['tasks'],
});

const PREFIX_ROUTE_SCOPES = Object.freeze([
  ['/maintenance/', ['maintenance']],
  ['/staff/', ['hr']],
]);

const NAV_KEY_SCOPES = Object.freeze({
  pms: ['frontdesk'],
  pms_operations: ['frontdesk'],
  reservation_calendar: ['frontdesk'],
  shift_handover: ['frontdesk'],
  early_late_pricing: ['frontdesk'],
  walkin: ['frontdesk'],
  room_map: ['frontdesk'],
  wake_up_calls: ['frontdesk'],
  housekeeping_status: ['housekeeping'],
  lost_found: ['housekeeping'],
  invoices: ['invoice'],
  konaklama_vergisi: ['invoice'],
  general_ledger: ['finance'],
  bank_reconciliation: ['finance'],
  fnb_costing: ['finance'],
  procurement: ['procurement'],
  supplies_market: ['procurement'],
  stock_rehber: ['stock', 'procurement'],
  group_bookings: ['sales'],
  block_management: ['sales'],
  deposit_tracking: ['sales'],
  group_folio: ['cashier'],
  channel_manager: ['channel_manager'],
  channels_hub: ['channel_manager'],
  cm_dashboard: ['channel_manager'],
  go_live_readiness: ['channel_manager'],
  unified_rate_manager: ['channel_manager'],
  rate_manager: ['channel_manager'],
  room_mapping_wizard: ['channel_manager'],
  travel_agent_arap: ['channel_manager'],
  agency_management: ['channel_manager'],
  incoming_agency_contracts: ['channel_manager'],
  agency_content: ['channel_manager'],
  b2b_analytics: ['channel_manager'],
  integration_hub: ['channel_manager', 'invoice'],
  reports: ['reports'],
  reports_basic: ['reports'],
  report_builder: ['reports'],
  report_scheduler: ['reports'],
  audit_timeline: ['reports'],
  urgent_message_report: ['reports'],
  recalled_messages_report: ['reports'],
  id_photo_view_report: ['reports'],
  no_show_analytics: ['reports'],
  sustainability_report: ['reports'],
  pos_dashboard: ['pos'],
  hr_hub: ['hr'],
  sales: ['sales'],
  sales_crm: ['sales'],
});

const MODULE_KEY_SCOPES = Object.freeze({
  pms: ['frontdesk'],
  reservation_calendar: ['frontdesk'],
  invoices: ['invoice'],
  channel_manager: ['channel_manager'],
  basic_reporting: ['reports'],
  reports: ['reports'],
  hr: ['hr'],
});

export const PMS_TAB_SCOPES = Object.freeze({
  frontdesk: ['frontdesk'],
  rooms: ['frontdesk'],
  guests: ['frontdesk'],
  bookings: ['frontdesk'],
  allotment: ['frontdesk'],
  concierge: ['frontdesk'],
  kbs: ['frontdesk'],
  kvkk: ['frontdesk'],
  housekeeping: ['housekeeping'],
  laundry: ['housekeeping'],
  cashier: ['cashier'],
  upsell: ['sales'],
  reports: ['reports'],
  flash: ['reports'],
  manager_report: ['reports'],
  revenue: ['reports'],
  tasks: ['tasks'],
  pos: ['pos'],
  feedback: ['sales'],
});

export const SUPPLEMENTAL_MODULE_NAV_ITEMS = Object.freeze([
  { key: 'cashier_workspace', label: 'Kasa', path: '/app/cashier', navGroup: 'backoffice', moduleScopes: ['cashier'] },
  { key: 'tasks_workspace', label: 'Görevler', path: '/app/tasks', navGroup: 'operations', navSection: 'daily', moduleScopes: ['tasks'] },
]);

function roleValue(user) {
  const rawRole = typeof user?.role === 'string' ? user.role : user?.role?.value;
  return typeof rawRole === 'string' ? rawRole.trim().toLowerCase() : '';
}

export function hasExplicitModuleScopes(user) {
  return !!user && Object.prototype.hasOwnProperty.call(user, 'module_scopes');
}

export function normalizeModuleScope(scope) {
  if (typeof scope !== 'string') return null;
  let normalized = scope.trim().toLowerCase().replaceAll('-', '_');
  if (normalized.endsWith('.*')) normalized = normalized.slice(0, -2);
  if (normalized === '*') return normalized;
  return MODULE_SCOPE_SET.has(normalized) ? normalized : null;
}

export function effectiveModuleScopes(user) {
  if (!user) return [];
  const role = roleValue(user);
  if (role === 'super_admin') return ['*'];

  if (hasExplicitModuleScopes(user)) {
    if (!Array.isArray(user.module_scopes)) return [];
    return [...new Set(user.module_scopes.map(normalizeModuleScope).filter(Boolean))];
  }

  return ROLE_DEFAULT_MODULE_SCOPES[role] || [];
}

export function hasModuleAccess(user, scope) {
  const granted = effectiveModuleScopes(user);
  if (granted.includes('*')) return true;
  const normalized = normalizeModuleScope(scope);
  if (!normalized) return false;
  return granted.includes(normalized);
}

export function hasAnyModuleAccess(user, scopes) {
  if (!Array.isArray(scopes) || scopes.length === 0) return true;
  if (scopes.includes(LEGACY_UNSCOPED_SURFACE)) {
    return roleValue(user) === 'super_admin' || !hasExplicitModuleScopes(user);
  }
  return scopes.some((scope) => hasModuleAccess(user, scope));
}

export function moduleScopesForPath(path) {
  if (typeof path !== 'string' || !path) return [LEGACY_UNSCOPED_SURFACE];
  const pathname = path.split('?')[0].split('#')[0];
  if (COMMON_ROUTE_PATHS.has(pathname)) return [];
  if (EXACT_ROUTE_SCOPES[pathname]) return [...EXACT_ROUTE_SCOPES[pathname]];

  if (pathname.startsWith('/folio-detail/')) return ['cashier'];
  for (const [prefix, scopes] of PREFIX_ROUTE_SCOPES) {
    if (pathname.startsWith(prefix)) return [...scopes];
  }
  return [LEGACY_UNSCOPED_SURFACE];
}

export function moduleScopesForRoute(routeConfig) {
  if (!routeConfig || routeConfig.type === 'public' || routeConfig.type === 'redirect') return [];
  if (Array.isArray(routeConfig.moduleScopes)) {
    const scopes = routeConfig.moduleScopes.map(normalizeModuleScope).filter(Boolean);
    return scopes.length ? scopes : [LEGACY_UNSCOPED_SURFACE];
  }
  return moduleScopesForPath(routeConfig.path || routeConfig.to || '');
}

export function moduleScopesForNavItem(item) {
  if (!item) return [LEGACY_UNSCOPED_SURFACE];
  if (COMMON_NAV_KEYS.has(item.key)) return [];
  if (Array.isArray(item.moduleScopes)) {
    const scopes = item.moduleScopes.map(normalizeModuleScope).filter(Boolean);
    return scopes.length ? scopes : [LEGACY_UNSCOPED_SURFACE];
  }
  if (NAV_KEY_SCOPES[item.key]) return [...NAV_KEY_SCOPES[item.key]];

  const pathScopes = moduleScopesForPath(item.path || '');
  if (!pathScopes.includes(LEGACY_UNSCOPED_SURFACE)) return pathScopes;

  if (MODULE_KEY_SCOPES[item.moduleKey]) return [...MODULE_KEY_SCOPES[item.moduleKey]];
  return [LEGACY_UNSCOPED_SURFACE];
}

export function moduleScopesForPmsTab(tabKey) {
  return [...(PMS_TAB_SCOPES[tabKey] || ['frontdesk'])];
}

export function supplementalModuleNavItems(user) {
  return SUPPLEMENTAL_MODULE_NAV_ITEMS.filter((item) => hasAnyModuleAccess(user, item.moduleScopes));
}
