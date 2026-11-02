import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { emptyKbsIdentity, kbsIdentityMissing, kbsStatusLabel } from '../kbs';
import { mobileTargetAllowed } from '../../navigation/routeAccess';

test('domestic / YKN require an eleven digit identity, not invented DOB', () => {
  const person = { ...emptyKbsIdentity(), name: 'Synthetic Guest', id_number: '12345678901' };
  assert.deepEqual(kbsIdentityMissing(person), []);
  assert.ok(kbsIdentityMissing({ ...person, id_number: 'bad' }).includes('id_number_invalid'));
  assert.deepEqual(kbsIdentityMissing({ ...person, nationality: 'DE', id_type: 'foreign_identity_card' }), []);
});
test('passport needs real name structure, valid past DOB, gender and passport', () => {
  const person = { ...emptyKbsIdentity(), name: 'Synthetic Guest', nationality: 'DE', id_type: 'passport',
    passport_number: 'SYNTHETIC', date_of_birth: '1990-05-12', gender: 'F' };
  assert.deepEqual(kbsIdentityMissing(person), []);
  assert.ok(kbsIdentityMissing({ ...person, date_of_birth: '2026-02-30' }).includes('birth_date_invalid'));
  assert.ok(kbsIdentityMissing({ ...person, date_of_birth: '2099-01-01' }).includes('birth_date_invalid'));
  assert.ok(kbsIdentityMissing({ ...person, name: 'Single', gender: '' }).includes('guest_name'));
});
test('two-view labels distinguish duplicates, missing, uncertainty and real acceptance', () => {
  assert.match(kbsStatusLabel({ status_reason: 'already_registered' }), /açık kayıt/);
  assert.match(kbsStatusLabel({ status_reason: 'missing_data' }), /Eksik bilgi/);
  assert.match(kbsStatusLabel({ status_reason: 'delivery_uncertain' }), /Teslim belirsiz/);
  assert.match(kbsStatusLabel({ status: 'done', kbs_test: true }), /resmî bildirim değil/);
  assert.equal(kbsStatusLabel({ status: 'done' }), 'Kurum kabulü alındı');
});
test('native KBS uses same operation and page permissions for menu and deep links', () => {
  assert.equal(mobileTargetAllowed({ role: 'front_desk' }, '/(frontdesk)/kbs'), true);
  assert.equal(mobileTargetAllowed({ role: 'guest' }, '/(frontdesk)/kbs'), false);
  assert.equal(mobileTargetAllowed({ role: 'housekeeping' }, '/(frontdesk)/kbs'), false);
  assert.equal(mobileTargetAllowed({ role: 'staff', page_access: { frontdesk: true }, effective_permissions: ['view_bookings'] }, '/(frontdesk)/kbs'), false);
  assert.equal(mobileTargetAllowed({ role: 'admin', page_access: { frontdesk: false }, effective_permissions: ['view_reports'] }, '/(frontdesk)/kbs'), false);
});
test('KBS data is not persisted offline, forms clear on blur, automatic mutations never retry', () => {
  const cache = readFileSync('src/cache/persister.ts', 'utf8');
  assert.match(cache, /!String\(q.queryKey\[0\]\).startsWith\('kbs-'\)/);
  const screen = readFileSync('app/(frontdesk)/kbs.tsx', 'utf8');
  assert.match(screen, /setEditing\(null\); setIdentity\(emptyKbsIdentity\(\)\)/);
  assert.match(screen, /retry: false/);
  assert.match(screen, /Gönderilen/);
  assert.match(screen, /Gönderilmeyen/);
});
