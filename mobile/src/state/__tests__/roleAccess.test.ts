// Unit coverage for the pure mobile role/entitlement predicates. Runs in plain
// Node via the built-in test runner (see `yarn test:unit` / tsconfig.unit.json)
// — no render harness, no extra dependencies. These functions feed the zustand
// `authStore` flags AND the (departments) hub/screen gating, so a regression
// here would silently surface or hide a department for the wrong role. The
// gating is COSMETIC — the backend still enforces every read/write — but it
// must stay faithful to the backend authorizer role-sets.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  canViewFinanceReports,
  hasApprovalsAccess,
  hasDepartmentAccess,
  hasHrAccess,
  hasMaintenanceAccess,
  hasMiceAccess,
  hasPosAccess,
  hasProcurementAccess,
  hasRevenueAccess,
  hasSpaAccess,
  isAllAccessRole,
  normalizeRole,
} from '../roleAccess';

// ── normalizeRole: backend role string → app role group ─────────────────────
test('normalizeRole maps the front-desk aliases', () => {
  for (const r of ['front_desk', 'reception', 'frontdesk', 'receptionist', 'FRONT_DESK']) {
    assert.equal(normalizeRole(r), 'front_desk', r);
  }
});

test('normalizeRole collapses every manager/admin alias to gm', () => {
  for (const r of ['gm', 'general_manager', 'manager', 'owner', 'super_admin', 'admin']) {
    assert.equal(normalizeRole(r), 'gm', r);
  }
});

test('normalizeRole maps housekeeping + guest aliases', () => {
  assert.equal(normalizeRole('housekeeper'), 'housekeeping');
  assert.equal(normalizeRole('hk'), 'housekeeping');
  assert.equal(normalizeRole('guest'), 'guest_app');
  assert.equal(normalizeRole('guest_app'), 'guest_app');
});

test('normalizeRole falls back to other for blank / unknown roles', () => {
  assert.equal(normalizeRole(undefined), 'other');
  assert.equal(normalizeRole(''), 'other');
  assert.equal(normalizeRole('finance'), 'other');
  assert.equal(normalizeRole('procurement'), 'other');
});

// ── isAllAccessRole: super_admin/admin browse every group ───────────────────
test('isAllAccessRole is true only for super_admin / admin (case-insensitive)', () => {
  assert.equal(isAllAccessRole('super_admin'), true);
  assert.equal(isAllAccessRole('ADMIN'), true);
  assert.equal(isAllAccessRole('supervisor'), false);
  assert.equal(isAllAccessRole('gm'), false);
  assert.equal(isAllAccessRole(undefined), false);
});

// ── Department predicates each match their backend authorizer role-set ───────
test('hasSpaAccess matches the require_spa_ops role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'front_desk', 'staff']) {
    assert.equal(hasSpaAccess(r), true, r);
  }
  for (const r of ['housekeeping', 'finance', 'sales', 'guest', undefined]) {
    assert.equal(hasSpaAccess(r), false, String(r));
  }
});

test('hasMiceAccess matches the require_mice_ops role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'sales']) {
    assert.equal(hasMiceAccess(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'finance', undefined]) {
    assert.equal(hasMiceAccess(r), false, String(r));
  }
});

test('hasMaintenanceAccess matches the housekeeping module role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'housekeeping']) {
    assert.equal(hasMaintenanceAccess(r), true, r);
  }
  for (const r of ['front_desk', 'finance', 'sales', undefined]) {
    assert.equal(hasMaintenanceAccess(r), false, String(r));
  }
});

test('canViewFinanceReports matches the VIEW_FINANCIAL_REPORTS role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance']) {
    assert.equal(canViewFinanceReports(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', undefined]) {
    assert.equal(canViewFinanceReports(r), false, String(r));
  }
});

test('hasProcurementAccess matches the require_procurement role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance', 'procurement']) {
    assert.equal(hasProcurementAccess(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'hr', undefined]) {
    assert.equal(hasProcurementAccess(r), false, String(r));
  }
});

test('hasHrAccess matches the VIEW_HR role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance', 'hr', 'hr_manager']) {
    assert.equal(hasHrAccess(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'procurement', undefined]) {
    assert.equal(hasHrAccess(r), false, String(r));
  }
});

test('hasRevenueAccess matches the view_revenue role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance']) {
    assert.equal(hasRevenueAccess(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', 'procurement', 'hr', undefined]) {
    assert.equal(hasRevenueAccess(r), false, String(r));
  }
});

test('hasPosAccess matches the require_module("pos") role-set', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'front_desk']) {
    assert.equal(hasPosAccess(r), true, r);
  }
  for (const r of ['housekeeping', 'finance', 'sales', 'procurement', 'hr', undefined]) {
    assert.equal(hasPosAccess(r), false, String(r));
  }
});

test('hasApprovalsAccess matches the union of finance + HR approval roles', () => {
  for (const r of ['super_admin', 'admin', 'supervisor', 'finance', 'hr', 'hr_manager']) {
    assert.equal(hasApprovalsAccess(r), true, r);
  }
  for (const r of ['front_desk', 'housekeeping', 'sales', undefined]) {
    assert.equal(hasApprovalsAccess(r), false, String(r));
  }
});

// ── hasDepartmentAccess: true iff at least one department gate opens ─────────
test('hasDepartmentAccess is true when any department predicate is true', () => {
  // housekeeping has only maintenance; sales has only mice; finance has several.
  assert.equal(hasDepartmentAccess('housekeeping'), true);
  assert.equal(hasDepartmentAccess('sales'), true);
  assert.equal(hasDepartmentAccess('finance'), true);
  assert.equal(hasDepartmentAccess('front_desk'), true); // spa
});

test('hasDepartmentAccess is false for roles with no department gate', () => {
  assert.equal(hasDepartmentAccess('guest'), false);
  assert.equal(hasDepartmentAccess('other'), false);
  assert.equal(hasDepartmentAccess(undefined), false);
});
