import assert from 'node:assert/strict';
import test from 'node:test';
import { hasServerAccess, mobileOperationAllowed } from '../roleAccess';

test('explicit workspace scopes and missing operation grants never fall back to role access', () => {
  assert.equal(hasServerAccess({ role: 'admin', module_scopes: [] }, 'finance', 'view_financial_reports'), false);
  assert.equal(hasServerAccess({ role: 'admin', effective_permissions: [] }, 'finance', 'view_financial_reports'), false);
  assert.equal(hasServerAccess({ role: 'admin', page_access: { finance: false }, effective_permissions: ['view_financial_reports'] }, 'finance', 'view_financial_reports'), false);
});

test('read grants never enable booking edits, collection, room updates or task assignment', () => {
  const reader = { role: 'staff', effective_permissions: ['view_bookings', 'view_hk_board'] };
  for (const permission of ['edit_booking', 'post_payment', 'update_room_status', 'assign_task']) {
    assert.equal(mobileOperationAllowed(reader, permission), false);
    assert.equal(mobileOperationAllowed({ ...reader, effective_permissions: [permission] }, permission), true);
  }
});

test('backend page context is complete, not a role or operation-name alias', () => {
  assert.equal(hasServerAccess({ role: 'staff', module_scopes: ['reports'], effective_permissions: ['view_reports', 'view_financial_reports'] }, 'reports', 'view_financial_reports'), true);
  assert.equal(hasServerAccess({ role: 'staff', page_access: { reports: true } }, 'finance', 'view_financial_reports'), false);
  assert.equal(hasServerAccess({ role: 'finance' }, 'finance', 'view_financial_reports'), undefined);
  assert.equal(hasServerAccess({ role: 'admin', page_access: {} }, 'finance'), false);
  assert.equal(hasServerAccess({ role: 'staff', module_scopes: ['maintenance'], effective_permissions: [] }, 'maintenance'), true);
});
