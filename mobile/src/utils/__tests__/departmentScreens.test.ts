// Unit coverage for the (departments) hub/screen decision helpers. Runs in
// plain Node via the built-in test runner (see `yarn test:unit` /
// tsconfig.unit.json) — no render harness, no extra dependencies. These guard
// the three Faz-3 read-only screens (Procurement / HR / Revenue) + the hub:
//   - the hub shows ONLY the tiles a role is entitled to (cosmetic gating),
//   - an unauthorized role hitting a screen redirects to the hub,
//   - the list/empty/error/data state machine resolves correctly,
//   - the tab sets stay intact.
// All gating is cosmetic; the backend still enforces every read/write.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  HR_TABS,
  PROCUREMENT_TABS,
  filterSubscribedHubTiles,
  groupHubTiles,
  hubModuleState,
  hubHasNoAccess,
  listViewState,
  screenHasAccess,
  screenRedirectsToHub,
  visibleHubTiles,
  type HubTile,
} from '../departmentScreens';

// ── visibleHubTiles: only entitled tiles, in render order ───────────────────
test('visibleHubTiles shows every tile for an all-access admin (render order)', () => {
  const expected: HubTile[] = [
    'spa',
    'mice',
    'cashier',
    'accounting',
    'maintenance',
    'procurement',
    'hr',
    'revenue',
    'pos',
  ];
  assert.deepEqual(visibleHubTiles('super_admin'), expected);
  assert.deepEqual(visibleHubTiles('admin'), expected);
});

test('visibleHubTiles for finance shows finance-gated tiles only', () => {
  // finance: view_finance_reports (cashier+accounting+revenue) + procurement + hr.
  assert.deepEqual(visibleHubTiles('finance'), [
    'cashier',
    'accounting',
    'procurement',
    'hr',
    'revenue',
  ]);
});

test('visibleHubTiles for front_desk shows spa + pos', () => {
  assert.deepEqual(visibleHubTiles('front_desk'), ['spa', 'pos']);
});

test('visibleHubTiles for housekeeping shows only maintenance', () => {
  assert.deepEqual(visibleHubTiles('housekeeping'), ['maintenance']);
});

test('visibleHubTiles for sales shows only mice', () => {
  assert.deepEqual(visibleHubTiles('sales'), ['mice']);
});

test('visibleHubTiles for supervisor shows the full set', () => {
  // supervisor holds every department gate in this app.
  assert.deepEqual(visibleHubTiles('supervisor'), [
    'spa',
    'mice',
    'cashier',
    'accounting',
    'maintenance',
    'procurement',
    'hr',
    'revenue',
    'pos',
  ]);
});

test('visibleHubTiles is empty for guest / unknown / missing roles', () => {
  assert.deepEqual(visibleHubTiles('guest'), []);
  assert.deepEqual(visibleHubTiles('other'), []);
  assert.deepEqual(visibleHubTiles(undefined), []);
});

test('filterSubscribedHubTiles removes explicitly disabled paid add-ons', () => {
  const tiles: HubTile[] = ['spa', 'mice', 'cashier', 'maintenance'];
  assert.deepEqual(filterSubscribedHubTiles(tiles, { spa: false, mice: false }), [
    'cashier',
    'maintenance',
  ]);
  assert.deepEqual(filterSubscribedHubTiles(tiles, { spa: true, mice: false }), [
    'spa',
    'cashier',
    'maintenance',
  ]);
});

test('unknown subscription never grants paid tiles or removes core workflows', () => {
  const tiles: HubTile[] = ['spa', 'mice'];
  assert.deepEqual(filterSubscribedHubTiles(tiles), []);
  assert.deepEqual(filterSubscribedHubTiles(tiles, {}), []);
  for (const tile of ['spa', 'mice', 'pos', 'revenue'] as const) {
    assert.equal(hubModuleState(tile), 'unknown');
    assert.equal(hubModuleState(tile, { modules: {} }), 'unknown');
  }
  // A denied/unavailable subscription read supplies no snapshot. Staff still
  // retain their role/page-authorized core navigation, including HR core reads.
  for (const tile of ['cashier', 'accounting', 'maintenance', 'procurement', 'hr'] as const) {
    assert.equal(hubModuleState(tile), 'enabled');
    assert.equal(hubModuleState(tile, { modules: { hr: false, maintenance: false } }), 'enabled');
  }
});

test('marketplace editions enable paid modules even when the legacy plan flag is false', () => {
  for (const [tile, key] of [['spa', 'spa'], ['mice', 'mice'], ['pos', 'pos_fnb'], ['revenue', 'revenue_management']] as const) {
    assert.equal(hubModuleState(tile, { modules: { [key]: false }, entitlements: { [key]: { editions: ['basic'] } } }), 'enabled');
  }
  assert.deepEqual(filterSubscribedHubTiles(['spa', 'mice'], { spa: false, mice: false }, { spa: { editions: ['pro'] } }), ['spa']);
});

test('subscription gating recognizes canonical POS keys and keeps partial/malformed snapshots unknown', () => {
  assert.equal(hubModuleState('pos', { modules: { pos_fnb: true } }), 'enabled');
  assert.equal(hubModuleState('pos', { modules: { pos_fnb_pro: true } }), 'enabled');
  assert.equal(hubModuleState('pos', { modules: { pos_fnb: false } }), 'disabled');
  assert.equal(hubModuleState('pos', { modules: { pos_basic: false } }), 'unknown');
  assert.equal(hubModuleState('pos', { modules: { pos_basic: false }, entitlements: {} }), 'disabled');
  assert.equal(hubModuleState('spa', { modules: { spa: false } }), 'disabled');
  assert.equal(hubModuleState('spa', { modules: { spa: 'true' }, entitlements: { spa: { editions: [] } } }), 'unknown');
  assert.equal(hubModuleState('spa', { modules: [], entitlements: { spa: { editions: [true] } } }), 'unknown');
  assert.equal(hubModuleState('revenue', { modules: { revenue_management: false, mobile_revenue: true } }), 'enabled');
});

test('hub respects server page/scope restrictions and existing screen access flags', () => {
  assert.deepEqual(visibleHubTiles('housekeeping', { maintenanceAccess: false }), []);
  assert.deepEqual(visibleHubTiles('front_desk', { moduleScopes: ['frontdesk'] }), ['spa']);
  assert.deepEqual(visibleHubTiles('front_desk', { pageAccess: { pos: false } }), ['spa']);
  assert.deepEqual(visibleHubTiles('front_desk', { moduleScopes: ['*'] }), ['spa', 'pos']);
  assert.deepEqual(visibleHubTiles('finance', { financeReports: false }), ['procurement', 'hr', 'revenue']);
  assert.deepEqual(visibleHubTiles('staff', { financeReports: true }), ['spa', 'cashier', 'accounting']);
  assert.deepEqual(visibleHubTiles('guest', { pageAccess: { pos: true, maintenance: true } }), []);
});

test('hub groups preserve each role-visible entry exactly once and omit empty groups', () => {
  const groups = groupHubTiles(visibleHubTiles('admin'));
  assert.deepEqual(groups.map((group) => group.key), ['operations', 'control', 'management']);
  const tiles = groups.flatMap((group) => group.tiles);
  assert.equal(tiles.length, 9);
  assert.equal(new Set(tiles).size, 9);
  assert.deepEqual(groupHubTiles(['maintenance']), [{ key: 'operations', tiles: ['maintenance'] }]);
  assert.deepEqual(groupHubTiles([]), []);
});

test('filterSubscribedHubTiles hides disabled POS and revenue modules', () => {
  const tiles: HubTile[] = ['pos', 'revenue', 'cashier'];
  assert.deepEqual(
    filterSubscribedHubTiles(tiles, {
      pos_basic: false,
      'pms.pos': false,
      revenue_management: false,
      mobile_revenue: false,
      'pms.revenue': false,
    }),
    ['cashier'],
  );
  assert.deepEqual(
    filterSubscribedHubTiles(tiles, {
      pos_basic: true,
      'pms.pos': false,
      revenue_management: false,
      mobile_revenue: false,
      'pms.revenue': true,
    }),
    tiles,
  );
});

// ── hubHasNoAccess: drives the hub's empty "no access" card ──────────────────
test('hubHasNoAccess is true only when no tile is visible', () => {
  assert.equal(hubHasNoAccess('guest'), true);
  assert.equal(hubHasNoAccess(undefined), true);
  assert.equal(hubHasNoAccess('front_desk'), false);
  assert.equal(hubHasNoAccess('finance'), false);
});

// ── screenHasAccess / screenRedirectsToHub: per-screen redirect guard ───────
test('procurement screen: authorized roles render, others redirect to the hub', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance', 'procurement']) {
    assert.equal(screenHasAccess('procurement', r), true, r);
    assert.equal(screenRedirectsToHub('procurement', r), false, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'hr', 'guest', undefined]) {
    assert.equal(screenHasAccess('procurement', r), false, String(r));
    assert.equal(screenRedirectsToHub('procurement', r), true, String(r));
  }
});

test('hr screen: authorized roles render, others redirect to the hub', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance', 'hr', 'hr_manager']) {
    assert.equal(screenHasAccess('hr', r), true, r);
    assert.equal(screenRedirectsToHub('hr', r), false, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'procurement', 'guest', undefined]) {
    assert.equal(screenHasAccess('hr', r), false, String(r));
    assert.equal(screenRedirectsToHub('hr', r), true, String(r));
  }
});

test('revenue screen: authorized roles render, others redirect to the hub', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance']) {
    assert.equal(screenHasAccess('revenue', r), true, r);
    assert.equal(screenRedirectsToHub('revenue', r), false, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'procurement', 'hr', 'guest', undefined]) {
    assert.equal(screenHasAccess('revenue', r), false, String(r));
    assert.equal(screenRedirectsToHub('revenue', r), true, String(r));
  }
});

// ── listViewState: loading → error → empty → data branch order ──────────────
test('listViewState reports loading first, even with a stale list or error', () => {
  assert.equal(listViewState({ loading: true, isEmpty: true }), 'loading');
  assert.equal(listViewState({ loading: true, isEmpty: false }), 'loading');
  assert.equal(
    listViewState({ loading: true, error: new Error('x'), isEmpty: false }),
    'loading',
  );
});

test('listViewState reports error before empty/data once loaded', () => {
  assert.equal(listViewState({ loading: false, error: new Error('x'), isEmpty: true }), 'error');
  // A truthy non-Error value still counts as an error (matches the component).
  assert.equal(listViewState({ loading: false, error: 'boom', isEmpty: false }), 'error');
});

test('listViewState reports empty when loaded, no error and nothing to show', () => {
  assert.equal(listViewState({ loading: false, isEmpty: true }), 'empty');
  assert.equal(listViewState({ loading: false, error: null, isEmpty: true }), 'empty');
});

test('listViewState reports data when loaded with rows present', () => {
  assert.equal(listViewState({ loading: false, isEmpty: false }), 'data');
  assert.equal(listViewState({ loading: false, error: undefined, isEmpty: false }), 'data');
});

// ── Tab sets: the screens render exactly these, in order ────────────────────
test('PROCUREMENT_TABS lists the four procurement sections in order', () => {
  assert.deepEqual([...PROCUREMENT_TABS], ['requests', 'pending', 'orders', 'deliveries']);
});

test('HR_TABS lists the three HR tabs in order', () => {
  assert.deepEqual([...HR_TABS], ['shifts', 'leave', 'attendance']);
});
