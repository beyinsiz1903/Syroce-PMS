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
