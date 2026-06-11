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

// Compute the tiles the departments hub shows for a RAW backend role. This is
// the single source of truth the hub renders from, so a role gaining/losing a
// tile is covered by one place. Cosmetic only — the backend still enforces
// every read/write behind each screen.
export function visibleHubTiles(rawRole: string | undefined): HubTile[] {
  const tiles: HubTile[] = [];
  if (hasSpaAccess(rawRole)) tiles.push('spa');
  if (hasMiceAccess(rawRole)) tiles.push('mice');
  // Cashier + Accounting both gate on view_finance_reports.
  if (canViewFinanceReports(rawRole)) tiles.push('cashier');
  if (canViewFinanceReports(rawRole)) tiles.push('accounting');
  if (hasMaintenanceAccess(rawRole)) tiles.push('maintenance');
  if (hasProcurementAccess(rawRole)) tiles.push('procurement');
  if (hasHrAccess(rawRole)) tiles.push('hr');
  if (hasRevenueAccess(rawRole)) tiles.push('revenue');
  if (hasPosAccess(rawRole)) tiles.push('pos');
  return tiles;
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
export const PROCUREMENT_TABS = ['requests', 'orders'] as const;
export type ProcurementTab = (typeof PROCUREMENT_TABS)[number];

export const HR_TABS = ['shifts', 'leave', 'attendance'] as const;
export type HrTab = (typeof HR_TABS)[number];
