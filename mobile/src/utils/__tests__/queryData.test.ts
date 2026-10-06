import assert from 'node:assert/strict';
import test from 'node:test';
import { asArray, countTodayWalkIns } from '../queryData';

test('asArray preserves list payloads', () => {
  const payload = [{ id: 'booking-1' }];
  assert.equal(asArray(payload), payload);
});

test('asArray rejects stale wrapped and empty payloads', () => {
  assert.deepEqual(asArray({ in_house: [] }), []);
  assert.deepEqual(asArray(null), []);
  assert.deepEqual(asArray(undefined), []);
});

test('countTodayWalkIns counts valid records and tolerates malformed API fields', () => {
  const payload = [
    { source: 'walk_in', check_in: '2026-10-06T12:00:00Z' },
    { source: 'WALK_IN', check_in: '2026-10-06' },
    { source: 'online', check_in: '2026-10-06' },
    { source: 17, check_in: { date: '2026-10-06' } },
    { source: 'walk_in', check_in: null },
    null,
  ];

  assert.equal(countTodayWalkIns(payload, '2026-10-06'), 2);
  assert.equal(countTodayWalkIns({ in_house: payload }, '2026-10-06'), 0);
});
