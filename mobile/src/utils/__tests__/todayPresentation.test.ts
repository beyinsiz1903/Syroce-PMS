import assert from 'node:assert/strict';
import test from 'node:test';
import {
  countLocalWalkIns,
  localDayISO,
  sortTodayBookings,
  todayBookingBalance,
  todayBookingTime,
  todayCountLabel,
  todayOccupancy,
} from '../todayPresentation';

test('Today preserves original USD/EUR amounts and labels without a TRY fallback or FX conversion', () => {
  for (const currency of ['USD', 'EUR']) {
    const balance = todayBookingBalance({ balance: '245.50', currency });
    assert.equal(balance?.amount, 245.5);
    assert.equal(balance?.currency, currency);
    assert.match(balance?.label || '', /245,50/);
    assert.doesNotMatch(balance?.label || '', /₺|TRY|TL/);
  }
  assert.equal(todayBookingBalance({ balance: 245.5, currency: ' eur ' })?.currency, 'EUR');
  assert.match(todayBookingBalance({ balance: 245.5, currency: 'TRY' })?.label || '', /₺|TRY/);
});

test('Today shows unverified currency explicitly and never fabricates a debt amount', () => {
  for (const currency of [undefined, null, '', 'invalid']) {
    const balance = todayBookingBalance({ balance: 245.5, currency });
    assert.equal(balance?.amount, 245.5);
    assert.equal(balance?.currency, undefined);
    assert.match(balance?.label || '', /para birimi belirtilmemiş/);
    assert.doesNotMatch(balance?.label || '', /₺|TRY|TL/);
  }
  for (const balance of [undefined, null, '', NaN, Infinity, 0, -5]) {
    assert.equal(todayBookingBalance({ balance, currency: 'USD' }), null);
  }
});

test('occupancy requires the complete server snapshot and accepts a genuine zero', () => {
  assert.deepEqual(todayOccupancy({ occupancy_pct: 29.4, occupied_rooms: 5, total_rooms: 17, occupancy_basis: 'current_room_state' }), { percentage: 29.4, occupied: 5, total: 17 });
  assert.deepEqual(todayOccupancy({ occupancy_pct: 25, occupied_rooms: 1, total_rooms: 4 }), { percentage: 25, occupied: 1, total: 4 });
  assert.deepEqual(todayOccupancy({ occupancy_pct: 0, occupied_rooms: 0, total_rooms: 4 }), { percentage: 0, occupied: 0, total: 4 });
  assert.deepEqual(todayOccupancy({ occupancy_pct: 14.3, occupied_rooms: 1, total_rooms: 7, currency: 'USD' }), { percentage: 14.3, occupied: 1, total: 7 });
  assert.equal(todayOccupancy({ occupancy_pct: 25, occupied_rooms: 1, total_rooms: 4 }, true), null);
});

test('occupancy omits missing, invalid, contradictory or zero-denominator snapshots', () => {
  const valid = { occupancy_pct: 25, occupied_rooms: 1, total_rooms: 4 };
  for (const invalid of [
    undefined, null, {}, { occupancy_pct: 25 },
    { ...valid, occupancy_pct: NaN }, { ...valid, occupancy_pct: Infinity },
    { ...valid, occupancy_pct: -1 }, { ...valid, occupancy_pct: 101 },
    { ...valid, occupancy_pct: '25' }, { ...valid, occupancy_pct: 80 },
    { ...valid, occupied_rooms: NaN }, { ...valid, occupied_rooms: -1 },
    { ...valid, occupied_rooms: 1.5 }, { ...valid, occupied_rooms: 5 },
    { ...valid, total_rooms: 0 }, { ...valid, total_rooms: Infinity },
    { ...valid, total_rooms: 4.5 }, { ...valid, total_rooms: undefined },
  ]) assert.equal(todayOccupancy(invalid), null);
});

test('today counts distinguish real zero from pending, failed and old cache data', () => {
  assert.equal(todayCountLabel([], false), '0');
  assert.equal(todayCountLabel([{ id: 'a' }], false), '1');
  assert.equal(todayCountLabel([], true), '—');
  assert.equal(todayCountLabel([{ id: 'a' }], true), '—');
  assert.equal(todayCountLabel(undefined, false), '—');
  assert.equal(todayCountLabel({ arrivals: [] }, false), '—');
});

test('date-only, missing and invalid booking dates never become a clock time', () => {
  assert.equal(todayBookingTime('2026-10-16'), null);
  assert.equal(todayBookingTime(undefined), null);
  assert.equal(todayBookingTime('2026-10-16T99:99:00Z'), null);
  assert.match(todayBookingTime('2026-10-16T14:30:00') || '', /14:30/);
});

test('today lists sort explicit times first without changing the source cache', () => {
  const data = [
    { id: 'date-only', guest_name: 'Zeynep', check_in: '2026-10-16' },
    { id: 'late', guest_name: 'Ali', check_in: '2026-10-16T16:00:00' },
    { id: 'early', guest_name: 'Mina', check_in: '2026-10-16T10:00:00' },
    null,
  ];
  assert.deepEqual(sortTodayBookings(data, 'check_in').map((booking) => booking.id), ['early', 'late', 'date-only']);
  assert.equal(data[0]?.id, 'date-only');
  assert.deepEqual(sortTodayBookings({ arrivals: [] }, 'check_in'), []);
});

test('walk-in dates follow the local calendar for timestamps and preserve date-only stays', () => {
  const localMorning = new Date(2026, 9, 16, 0, 30);
  const localPreviousDay = new Date(2026, 9, 15, 23, 30);
  assert.equal(localDayISO(localMorning), '2026-10-16');
  assert.equal(countLocalWalkIns([
    { source: 'walk_in', check_in: localMorning.toISOString() },
    { source: 'WALK_IN', check_in: '2026-10-16' },
    { source: 'walk_in', check_in: localPreviousDay.toISOString() },
    { source: 'online', check_in: '2026-10-16' },
    { source: 'walk_in', check_in: 'invalid' },
    { source: 'walk_in', check_in: null },
    null,
  ], '2026-10-16'), 2);
  assert.equal(countLocalWalkIns({ in_house: [] }, '2026-10-16'), 0);
});
