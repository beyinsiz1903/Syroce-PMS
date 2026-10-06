import assert from 'node:assert/strict';
import test from 'node:test';
import { asArray } from '../queryData';

test('asArray preserves list payloads', () => {
  const payload = [{ id: 'booking-1' }];
  assert.equal(asArray(payload), payload);
});

test('asArray rejects stale wrapped and empty payloads', () => {
  assert.deepEqual(asArray({ in_house: [] }), []);
  assert.deepEqual(asArray(null), []);
  assert.deepEqual(asArray(undefined), []);
});
