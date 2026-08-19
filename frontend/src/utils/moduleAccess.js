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

const EXACT_ROUTE_SCOPES = Object.freeze({
  '/app/pms': ['frontdesk'],
  '/pms': ['frontdesk'],
  '/app/reservation-calendar': ['frontdesk'],
  '/reservation-calendar': ['frontdesk'],
  '/walkin': ['frontdesk'],
  '/room-map': ['frontdesk'],
  '/frontdesk/audit-checklist': ['frontdesk'],

  '/housekeeping': ['housekeeping'],
  '/housekeeping-status': ['housekeeping'],

  '/app/cashier': ['cashier'],
  '/folio-detail': ['cashier'],

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
  '/app/stock-rehber': ['stock', 'procurement'],
  '/hotel-inventory': ['stock'],
  '/hotel-inventory/transfers': ['stock'],

  '/sales': ['sales'],
  '/group-sales': ['sales'],
  '/sales-crm': ['sales'],

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

  '/channel-manager': ['channel_manager'],
  '/app/channel-manager': ['channel_manager'],
  '/channels': ['channel_manager'],
  '/app/channels': ['channel_manager'],
  '/mapping-manager': ['channel_manager'],
  '/room-mapping-wizard': ['channel_manager'],
  '/unified-rate-manager': ['channel_manager'],

  '/pos': ['pos'],
  '/pos/terminal': ['pos'],
  '/pos-extensions': ['pos'],
  '/staff/room-service': ['pos'],

  '/app/tasks': ['tasks'],
});

const PREFIX_ROUTE_SCOPES = Object.freeze([
  ['/maintenance/', ['maintenance']],
  ['/staff/', ['hr']],
]);

const NAV_KEY_SCOPES = Object.freeze({
  pms: ['frontdesk'],
  reservation_calendar: ['frontdesk'],
  housekeeping_status: ['housekeeping'],
  invoices: ['invoice'],
  general_ledger: ['finance'],
  bank_reconciliation: ['finance'],
  procurement: ['procurement'],
  stock_rehber: ['stock', 'procurement'],
  channel_manager: ['channel_manager'],
  unified_rate_manager: ['channel_manager'],
  rate_manager: ['channel_manager'],
  reports: ['reports'],
  reports_basic: ['reports'],
  report_builder: ['reports'],
  pos_dashboard: ['pos'],
  hr_hub: ['hr'],
  sales: ['sales'],
  sales_crm: ['sales'],
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
  { key: 'tasks_workspace', label: 'Görevler', path: '/app/tasks', navGroup: 'operations', moduleScopes: ['tasks'] },
]);

export function normalizeModuleScope(scope) {
  if (typeof scope !== 'string') return null;
  let normalized = scope.trim().toLowerCase().replaceAll('-', '_');
  if (normalized.endsWith('.*')) normalized = normalized.slice(0, -2);
  if (normalized === '*') return normalized;
  return MODULE_SCOPE_SET.has(normalized) ? normalized : null;
}

export function effectiveModuleScopes(user) {
  if (!user) return [];
  const rawRole = typeof user.role === 'string' ? user.role : user.role?.value;
  const role = typeof rawRole === 'string' ? rawRole.trim().toLowerCase() : '';
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

export function hasAnyModuleAccess(user, scopes) {
  if (!Array.isArray(scopes) || scopes.length === 0) return true;
  return scopes.some((scope) => hasModuleAccess(user, scope));
}

export function moduleScopesForPath(path) {
  if (typeof path !== 'string' || !path) return [];
  const pathname = path.split('?')[0].split('#')[0];
  if (EXACT_ROUTE_SCOPES[pathname]) return [...EXACT_ROUTE_SCOPES[pathname]];

  if (pathname.startsWith('/folio-detail/')) return ['cashier'];
  for (const [prefix, scopes] of PREFIX_ROUTE_SCOPES) {
    if (pathname.startsWith(prefix)) return [...scopes];
  }
  return [];
}

export function moduleScopesForRoute(routeConfig) {
  if (!routeConfig || routeConfig.type === 'public') return [];
  if (Array.isArray(routeConfig.moduleScopes)) return routeConfig.moduleScopes.map(normalizeModuleScope).filter(Boolean);
  return moduleScopesForPath(routeConfig.path || routeConfig.to || '');
}

export function moduleScopesForNavItem(item) {
  if (!item) return [];
  if (Array.isArray(item.moduleScopes)) return item.moduleScopes.map(normalizeModuleScope).filter(Boolean);
  if (NAV_KEY_SCOPES[item.key]) return [...NAV_KEY_SCOPES[item.key]];
  return moduleScopesForPath(item.path || '');
}

export function moduleScopesForPmsTab(tabKey) {
  return [...(PMS_TAB_SCOPES[tabKey] || ['frontdesk'])];
}

export function supplementalModuleNavItems(user) {
  return SUPPLEMENTAL_MODULE_NAV_ITEMS.filter((item) => hasAnyModuleAccess(user, item.moduleScopes));
}
