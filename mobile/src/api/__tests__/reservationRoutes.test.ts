import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const source = readFileSync(resolve(process.cwd(), 'src/api/reservations.ts'), 'utf8');

test('the mobile account read uses the mounted PMS namespace and encodes the booking id', () => {
  const accountRead = source.slice(source.indexOf('export async function getReservationFullDetail'), source.indexOf('// Mutations'));
  assert.match(accountRead, /api\.get<ReservationFullDetail>\(`\/api\/pms\/reservations\/\$\{encodeURIComponent\(id\)\}\/full-detail`\)/);
  assert.doesNotMatch(accountRead, /`\/api\/reservations\//);
});

test('account reads reject a mismatched booking and never substitute an operational folio balance', () => {
  const accountRead = source.slice(source.indexOf('export async function getReservationFullDetail'), source.indexOf('// Mutations'));
  assert.match(accountRead, /res\?\.booking\?\.id !== id/);
  assert.doesNotMatch(accountRead, /getFolioForBooking|\/api\/frontdesk\/folio\//);
});
