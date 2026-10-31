// Pure decision helpers for the (departments) area: which hub tiles a role
// sees, whether a gated department screen self-redirects to the hub, and the
// loading/error/empty/data state machine the list sections share. Kept free of
// React/React-Native imports so the plain-Node unit test runner can exercise
// them (mirrors the `availabilityFilters` pattern). The screens import these so
// the tests guard the real render decisions, not a parallel copy.
import {
  canViewFinanceReports,
  hasHrAccess,
  hasMaintenanceAccess,
  hasMiceAccess,
  hasPosAccess,
  hasProcurementAccess,
  hasRevenueAccess,
  hasSpaAccess,
  deriveMobileAccess,
  type ServerAccessContext,
} from '../state/roleAccess';

// Hub tile keys, in the exact render order of app/(departments)/index.tsx.
export type HubTile =
  | 'spa'
  | 'mice'
  | 'cashier'
  | 'accounting'
  | 'maintenance'
  | 'procurement'
  | 'hr'
  | 'revenue'
  | 'pos';

export type HubAccessContext = {
  user?: ServerAccessContext;
  financeReports?: boolean;
  maintenanceAccess?: boolean;
  pageAccess?: Record<string, boolean>;
  moduleScopes?: readonly string[] | null;
};

// Only exact backend mappings are used. SPA/MICE and the revenue-engine do
// not have matching page/module scopes in user_access_catalog.json.
const HUB_WORKSPACES: Partial<Record<HubTile, { page: string; scope: string }>> = {
  cashier: { page: 'cashier', scope: 'cashier' },
  accounting: { page: 'finance', scope: 'finance' },
  maintenance: { page: 'maintenance', scope: 'maintenance' },
  procurement: { page: 'procurement', scope: 'procurement' },
  hr: { page: 'hr', scope: 'hr' },
  pos: { page: 'pos', scope: 'pos' },
};

// Compute the tiles the departments hub shows for a RAW backend role. This is
// the single source of truth the hub renders from, so a role gaining/losing a
// tile is covered by one place. Cosmetic only — the backend still enforces
// every read/write behind each screen.
export function visibleHubTiles(rawRole: string | undefined, access: HubAccessContext = {}): HubTile[] {
  if (access.user) {
    const a = deriveMobileAccess(access.user);
    if (a.role === 'guest_app') return [];
    return (['spa', 'mice', 'cashier', 'accounting', 'maintenance', 'procurement', 'hr', 'revenue', 'pos'] as const)
      .filter((key) => a[`${key}Access`]);
  }
  const tiles: HubTile[] = [];
  if (hasSpaAccess(rawRole)) tiles.push('spa');
  if (hasMiceAccess(rawRole)) tiles.push('mice');
  // Cashier + Accounting both gate on view_finance_reports.
  if (access.financeReports ?? canViewFinanceReports(rawRole)) tiles.push('cashier', 'accounting');
  if (access.maintenanceAccess ?? hasMaintenanceAccess(rawRole)) tiles.push('maintenance');
  if (hasProcurementAccess(rawRole)) tiles.push('procurement');
  if (hasHrAccess(rawRole)) tiles.push('hr');
  if (hasRevenueAccess(rawRole)) tiles.push('revenue');
  if (hasPosAccess(rawRole)) tiles.push('pos');
  return tiles.filter((tile) => {
    if (rawRole?.toLowerCase() === 'super_admin') return true;
    const workspace = HUB_WORKSPACES[tile];
    if (!workspace) return true;
    if (access.pageAccess?.[workspace.page] === false) return false;
    if (Array.isArray(access.moduleScopes)
      && !access.moduleScopes.includes('*') && !access.moduleScopes.includes(workspace.scope)) return false;
    return true;
  });
}

export type HubModuleState = 'enabled' | 'disabled' | 'unknown';
export type HubSubscriptionSnapshot = { modules?: unknown; entitlements?: unknown };

const PAID_MODULE_KEYS: Partial<Record<HubTile, readonly string[]>> = {
  spa: ['spa'],
  mice: ['mice'],
  pos: ['pos_fnb', 'pos_fnb_basic', 'pos_fnb_pro', 'pos_basic', 'pms.pos'],
  revenue: ['revenue_management', 'mobile_revenue', 'pms.revenue'],
};
const EDITION_KEYS: Partial<Record<HubTile, readonly string[]>> = {
  spa: ['spa'], mice: ['mice'], pos: ['pos_fnb'], revenue: ['revenue_management', 'revenue'],
};

function objectRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

/** Navigation eligibility, not a health check or a substitute for backend RBAC. */
export function hubModuleState(tile: HubTile, snapshot?: HubSubscriptionSnapshot): HubModuleState {
  const keys = PAID_MODULE_KEYS[tile];
  // These screens have role/page guards but no whole-screen subscription flag.
  // In particular, missing HR feature editions must not hide its core reads.
  if (!keys) return 'enabled';
  const modules = objectRecord(snapshot?.modules);
  const entitlements = objectRecord(snapshot?.entitlements);
  const editionEnabled = (EDITION_KEYS[tile] || []).some((key) => {
    const entry = objectRecord(entitlements?.[key]);
    return Array.isArray(entry?.editions) && entry.editions.some((edition) => typeof edition === 'string' && !!edition.trim());
  });
  if (editionEnabled || keys.some((key) => modules?.[key] === true)) return 'enabled';
  // An absent/partial map is unknown, not a paid-module grant or a denial.
  const known = keys.map((key) => modules?.[key]).filter((value) => typeof value === 'boolean');
  const canonicalDenied = modules?.[keys[0]] === false;
  return known.length > 0 && known.every((value) => value === false) && (canonicalDenied || !!entitlements)
    ? 'disabled' : 'unknown';
}

// Compatibility selector for callers that need only confirmed entry points.
export function filterSubscribedHubTiles(
  tiles: HubTile[],
  modules?: Record<string, boolean>,
  entitlements?: unknown,
): HubTile[] {
  return tiles.filter((tile) => hubModuleState(tile, { modules, entitlements }) === 'enabled');
}

export type HubGroupKey = 'operations' | 'control' | 'management';
const HUB_GROUPS: { key: HubGroupKey; tiles: readonly HubTile[] }[] = [
  { key: 'operations', tiles: ['pos', 'spa', 'mice', 'maintenance'] },
  { key: 'control', tiles: ['cashier', 'accounting'] },
  { key: 'management', tiles: ['procurement', 'hr', 'revenue'] },
];

export function groupHubTiles(tiles: HubTile[]): { key: HubGroupKey; tiles: HubTile[] }[] {
  return HUB_GROUPS.map((group) => ({ key: group.key, tiles: group.tiles.filter((tile) => tiles.includes(tile)) }))
    .filter((group) => group.tiles.length > 0);
}

// True when the role sees no department tile at all (the hub shows its empty
// "no access" card).
export function hubHasNoAccess(rawRole: string | undefined): boolean {
  return visibleHubTiles(rawRole).length === 0;
}

// The Faz-3 read-only department screens that self-redirect to the hub when the
// signed-in role lacks the cosmetic entitlement (mirrors the `<Redirect>` guard
// at the top of each screen).
export type GatedScreen = 'procurement' | 'hr' | 'revenue';

export function screenHasAccess(screen: GatedScreen, rawRole: string | undefined): boolean {
  switch (screen) {
    case 'procurement':
      return hasProcurementAccess(rawRole);
    case 'hr':
      return hasHrAccess(rawRole);
    case 'revenue':
      return hasRevenueAccess(rawRole);
  }
}

// True when the screen should `<Redirect>` to the departments hub for this role.
export function screenRedirectsToHub(screen: GatedScreen, rawRole: string | undefined): boolean {
  return !screenHasAccess(screen, rawRole);
}

// The list/empty/error/data state machine shared by every department list
// section — mirrors <DepartmentListState>'s branch order (loading → error →
// empty → data). 'data' means the caller renders the rows itself.
export type ListViewState = 'loading' | 'error' | 'empty' | 'data';

export function listViewState(input: {
  loading: boolean;
  error?: unknown;
  isEmpty: boolean;
}): ListViewState {
  if (input.loading) return 'loading';
  if (input.error) return 'error';
  if (input.isEmpty) return 'empty';
  return 'data';
}

// Tab values each multi-tab department screen renders, in display order. The
// screens map over these so the tab set lives in one place.
export const PROCUREMENT_TABS = ['requests', 'pending', 'orders', 'deliveries'] as const;
export type ProcurementTab = (typeof PROCUREMENT_TABS)[number];

export const HR_TABS = ['shifts', 'leave', 'attendance'] as const;
export type HrTab = (typeof HR_TABS)[number];
