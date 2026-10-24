import assert from 'node:assert/strict';
import test from 'node:test';
import { DEMO_TOKEN, previewResponse } from './preview-api.mjs';

const read = (path) => previewResponse({ path, authorization: `Bearer ${DEMO_TOKEN}` });

test('read-only preview follows the canonical PMS account route', () => {
  const result = read('/api/pms/reservations/booking-ayse/full-detail');
  assert.equal(result.status, 200);
  assert.equal(result.body.booking.id, 'booking-ayse');
  assert.equal(result.body.summary.gross_total, 8000);
  assert.equal(result.body.payments[0].amount, 3000);
  assert.equal(result.body.summary.reservation_total_due, 5000);
  assert.equal(read('/api/reservations/booking-ayse/full-detail').status, 404);
});

test('other reservation reads keep their separate API namespace', () => {
  assert.equal(read('/api/reservations/booking-ayse/details-enhanced').status, 200);
  assert.equal(read('/api/reservations/booking-ayse/ota-details').status, 200);
  assert.equal(read('/api/pms/reservations/unknown/full-detail').status, 404);
});

test('the preview account route requires a demo session and cannot write', () => {
  const path = '/api/pms/reservations/booking-ayse/full-detail';
  assert.equal(previewResponse({ path }).status, 401);
  assert.equal(previewResponse({ path, method: 'POST', authorization: `Bearer ${DEMO_TOKEN}` }).status, 409);
});
