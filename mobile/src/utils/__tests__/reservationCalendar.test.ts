// Unit coverage for the reservation calendar showcase pure helpers (Task #509).
// Runs in plain Node via the built-in test runner (see `yarn test:unit` /
// tsconfig.unit.json) — no RN, no render harness. Locks in the placement math
// (bars span exactly their booked nights, clipped to the window), the
// drag-drop drop-target clamping, the pinch-zoom view stepping, and the move
// plan that the screen sends to the backend.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDayList,
  computeDropTarget,
  hasMove,
  isActiveReservation,
  nextViewFromZoom,
  placeReservations,
  planMove,
  roomCalStatus,
  toDateOnly,
  type CalReservation,
} from '../reservationCalendar';

// ── toDateOnly / diffDays ──────────────────────────────────────────────────
test('toDateOnly: extracts date from date or datetime, rejects junk', () => {
  assert.equal(toDateOnly('2026-06-12'), '2026-06-12');
  assert.equal(toDateOnly('2026-06-12T14:30:00Z'), '2026-06-12');
  assert.equal(toDateOnly(''), undefined);
  assert.equal(toDateOnly('not-a-date'), undefined);
});

// ── roomCalStatus ──────────────────────────────────────────────────────────
test('roomCalStatus: ooo/cleaning win over occupancy, then occupied, then free', () => {
  assert.equal(roomCalStatus('out_of_order', true), 'out_of_order');
  assert.equal(roomCalStatus('maintenance', false), 'out_of_order');
  assert.equal(roomCalStatus('cleaning', true), 'cleaning');
  assert.equal(roomCalStatus('dirty', false), 'cleaning');
  assert.equal(roomCalStatus('available', true), 'occupied');
  assert.equal(roomCalStatus('occupied', false), 'occupied');
  assert.equal(roomCalStatus('available', false), 'available');
  assert.equal(roomCalStatus(undefined, false), 'available');
});

// ── isActiveReservation ────────────────────────────────────────────────────
test('isActiveReservation: released statuses do not hold inventory', () => {
  assert.equal(isActiveReservation('confirmed'), true);
  assert.equal(isActiveReservation('checked_in'), true);
  assert.equal(isActiveReservation('cancelled'), false);
  assert.equal(isActiveReservation('no_show'), false);
});

// ── placeReservations ──────────────────────────────────────────────────────
function res(over: Partial<CalReservation> = {}): CalReservation {
  return {
    id: over.id ?? 'r1',
    room_id: 'room_id' in over ? over.room_id : 'room-a',
    guest_name: over.guest_name ?? 'Ada',
    status: over.status ?? 'confirmed',
    check_in: over.check_in ?? '2026-06-12',
    check_out: over.check_out ?? '2026-06-14',
    total_amount: over.total_amount,
    vip_status: over.vip_status,
  };
}

test('placeReservations: a 12->14 stay spans exactly two columns (checkout exclusive)', () => {
  const days = buildDayList('2026-06-12', 7);
  const bars = placeReservations([res()], days);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].startOffset, 0);
  assert.equal(bars[0].nights, 2);
  assert.equal(bars[0].clippedStart, false);
  assert.equal(bars[0].clippedEnd, false);
});

test('placeReservations: clips a stay that straddles the left/right edges', () => {
  const days = buildDayList('2026-06-12', 5); // 12..16
  const bars = placeReservations(
    [res({ check_in: '2026-06-10', check_out: '2026-06-20' })],
    days,
  );
  assert.equal(bars.length, 1);
  assert.equal(bars[0].startOffset, 0);
  assert.equal(bars[0].nights, 5);
  assert.equal(bars[0].clippedStart, true);
  assert.equal(bars[0].clippedEnd, true);
});

test('placeReservations: drops out-of-window, released, room-less and inverted stays', () => {
  const days = buildDayList('2026-06-12', 3); // 12,13,14
  const bars = placeReservations(
    [
      res({ id: 'past', check_in: '2026-06-01', check_out: '2026-06-05' }),
      res({ id: 'cxl', status: 'cancelled' }),
      res({ id: 'noroom', room_id: undefined }),
      res({ id: 'inverted', check_in: '2026-06-14', check_out: '2026-06-12' }),
      res({ id: 'ok' }),
    ],
    days,
  );
  assert.deepEqual(
    bars.map((b) => b.reservation.id),
    ['ok'],
  );
});

// ── computeDropTarget ──────────────────────────────────────────────────────
test('computeDropTarget: snaps to nearest cell and reports what changed', () => {
  const t = computeDropTarget({
    startOffset: 1,
    startRoomIndex: 0,
    dx: 160, // 2 columns at 80px
    dy: 56, // 1 row at 56px
    dayWidth: 80,
    rowHeight: 56,
    dayCount: 10,
    roomCount: 5,
    nights: 2,
  });
  assert.equal(t.dayOffset, 3);
  assert.equal(t.roomIndex, 1);
  assert.equal(t.changedDay, true);
  assert.equal(t.changedRoom, true);
});

test('computeDropTarget: clamps inside the grid (day respects nights, room respects roster)', () => {
  const t = computeDropTarget({
    startOffset: 8,
    startRoomIndex: 4,
    dx: 9999,
    dy: 9999,
    dayWidth: 80,
    rowHeight: 56,
    dayCount: 10,
    roomCount: 5,
    nights: 3,
  });
  assert.equal(t.dayOffset, 7); // dayCount(10) - nights(3)
  assert.equal(t.roomIndex, 4); // roomCount(5) - 1
});

test('computeDropTarget: a tiny jiggle changes nothing', () => {
  const t = computeDropTarget({
    startOffset: 2,
    startRoomIndex: 1,
    dx: 5,
    dy: 5,
    dayWidth: 80,
    rowHeight: 56,
    dayCount: 10,
    roomCount: 5,
    nights: 1,
  });
  assert.equal(t.dayOffset, 2);
  assert.equal(t.roomIndex, 1);
  assert.equal(t.changedDay, false);
  assert.equal(t.changedRoom, false);
});

// ── nextViewFromZoom ───────────────────────────────────────────────────────
test('nextViewFromZoom: pinch out zooms in one step, pinch in zooms out one step', () => {
  assert.equal(nextViewFromZoom('month', 1.4), 'week');
  assert.equal(nextViewFromZoom('week', 1.4), 'day');
  assert.equal(nextViewFromZoom('day', 1.4), 'day'); // already most detailed
  assert.equal(nextViewFromZoom('day', 0.6), 'week');
  assert.equal(nextViewFromZoom('week', 0.6), 'month');
  assert.equal(nextViewFromZoom('month', 0.6), 'month'); // already overview
  assert.equal(nextViewFromZoom('week', 1.05), 'week'); // below threshold
});

// ── planMove / hasMove ─────────────────────────────────────────────────────
test('planMove: room change only emits an assign, date change preserves nights', () => {
  const roomOnly = planMove({
    changedRoom: true,
    changedDay: false,
    targetRoomId: 'room-b',
    newCheckIn: '2026-06-12',
    nights: 2,
  });
  assert.deepEqual(roomOnly, { assignRoomId: 'room-b' });
  assert.equal(hasMove(roomOnly), true);

  const dateOnly = planMove({
    changedRoom: false,
    changedDay: true,
    targetRoomId: undefined,
    newCheckIn: '2026-06-15',
    nights: 2,
  });
  assert.deepEqual(dateOnly, { newCheckIn: '2026-06-15', newCheckOut: '2026-06-17' });

  const both = planMove({
    changedRoom: true,
    changedDay: true,
    targetRoomId: 'room-b',
    newCheckIn: '2026-06-15',
    nights: 3,
  });
  assert.deepEqual(both, {
    assignRoomId: 'room-b',
    newCheckIn: '2026-06-15',
    newCheckOut: '2026-06-18',
  });

  const none = planMove({
    changedRoom: false,
    changedDay: false,
    targetRoomId: undefined,
    newCheckIn: '2026-06-12',
    nights: 1,
  });
  assert.deepEqual(none, {});
  assert.equal(hasMove(none), false);
});
