// Unit coverage for the mobile availability grid (room x day) occupancy logic.
// Runs in plain Node via the built-in test runner (see `yarn test:unit` /
// tsconfig.unit.json) — no render harness, no extra dependencies. Guards the
// precedence rules (occupied > blocked > free), OOO/OOS mapping, block date
// boundaries, and the allow_sell exception. A regression here could show a busy
// room as free (double-booking risk) or a free room as blocked.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  addDaysISO,
  buildDayList,
  isBlockedRoomStatus,
  cellStatusFromRoom,
  blockCoversDay,
  buildAvailabilityGrid,
  type GridRoomInput,
  type GridBlockInput,
} from '../availabilityGrid';

// ── addDaysISO: timezone-stable date math ──────────────────────────────────
test('addDaysISO advances a plain date and crosses month/year boundaries', () => {
  assert.equal(addDaysISO('2026-06-10', 1), '2026-06-11');
  assert.equal(addDaysISO('2026-06-10', 0), '2026-06-10');
  assert.equal(addDaysISO('2026-06-30', 1), '2026-07-01');
  assert.equal(addDaysISO('2026-12-31', 1), '2027-01-01');
});

// ── buildDayList: the ordered span of days ─────────────────────────────────
test('buildDayList returns the inclusive run of day strings from the start', () => {
  assert.deepEqual(buildDayList('2026-06-10', 3), [
    '2026-06-10',
    '2026-06-11',
    '2026-06-12',
  ]);
  assert.deepEqual(buildDayList('2026-06-10', 0), []);
  assert.deepEqual(buildDayList('2026-06-10', 1), ['2026-06-10']);
});

// ── isBlockedRoomStatus: OOO/OOS room states ───────────────────────────────
test('isBlockedRoomStatus flags every unsellable room state, case-insensitively', () => {
  for (const s of ['out_of_order', 'out_of_service', 'maintenance', 'ooo', 'oos']) {
    assert.equal(isBlockedRoomStatus(s), true, s);
    assert.equal(isBlockedRoomStatus(s.toUpperCase()), true, s.toUpperCase());
  }
});

test('isBlockedRoomStatus is false for sellable / unknown / blank statuses', () => {
  assert.equal(isBlockedRoomStatus('available'), false);
  assert.equal(isBlockedRoomStatus('clean'), false);
  assert.equal(isBlockedRoomStatus(''), false);
  assert.equal(isBlockedRoomStatus(undefined), false);
});

// ── cellStatusFromRoom: baseline cell from the day's availability payload ───
test('cellStatusFromRoom maps an available room to free', () => {
  assert.equal(cellStatusFromRoom({ id: 'r1', available: true }), 'free');
  // available undefined / missing is treated as not-unavailable -> free.
  assert.equal(cellStatusFromRoom({ id: 'r1' }), 'free');
});

test('cellStatusFromRoom maps an unavailable booked room to occupied', () => {
  assert.equal(
    cellStatusFromRoom({ id: 'r1', available: false, reason: 'Booked by guest' }),
    'occupied',
  );
});

test('cellStatusFromRoom maps an unavailable non-booking reason to blocked', () => {
  assert.equal(
    cellStatusFromRoom({ id: 'r1', available: false, reason: 'maintenance hold' }),
    'blocked',
  );
  // Unavailable with no reason at all is conservative -> blocked, not occupied.
  assert.equal(cellStatusFromRoom({ id: 'r1', available: false }), 'blocked');
});

test('cellStatusFromRoom: OOO/OOS room status wins over the booking calendar', () => {
  // Even when the room looks bookable (available !== false), an OOO room is
  // blocked.
  assert.equal(
    cellStatusFromRoom({ id: 'r1', status: 'out_of_order', available: true }),
    'blocked',
  );
  // And it stays blocked (never "occupied") even with a booked reason.
  assert.equal(
    cellStatusFromRoom({
      id: 'r1',
      status: 'OOO',
      available: false,
      reason: 'booked',
    }),
    'blocked',
  );
});

// ── blockCoversDay: start-inclusive, end-exclusive range ───────────────────
test('blockCoversDay is inclusive at the start day', () => {
  const block: GridBlockInput = { start_date: '2026-06-10', end_date: '2026-06-12' };
  assert.equal(blockCoversDay(block, '2026-06-10'), true);
});

test('blockCoversDay is exclusive at the end day (checkout-day release)', () => {
  const block: GridBlockInput = { start_date: '2026-06-10', end_date: '2026-06-12' };
  assert.equal(blockCoversDay(block, '2026-06-11'), true);
  assert.equal(blockCoversDay(block, '2026-06-12'), false);
  assert.equal(blockCoversDay(block, '2026-06-09'), false);
});

test('blockCoversDay treats missing start/end as open-ended', () => {
  assert.equal(blockCoversDay({ end_date: '2026-06-12' }, '2026-01-01'), true);
  assert.equal(blockCoversDay({ start_date: '2026-06-10' }, '2030-01-01'), true);
  assert.equal(blockCoversDay({}, '2026-06-10'), true);
});

test('blockCoversDay never covers an allow_sell block', () => {
  const block: GridBlockInput = {
    start_date: '2026-06-10',
    end_date: '2026-06-12',
    allow_sell: true,
  };
  assert.equal(blockCoversDay(block, '2026-06-10'), false);
  assert.equal(blockCoversDay(block, '2026-06-11'), false);
});

// ── buildAvailabilityGrid: full assembly + precedence ──────────────────────
test('buildAvailabilityGrid unions rooms across days and sorts numerically', () => {
  const days = buildDayList('2026-06-10', 2);
  const perDay: GridRoomInput[][] = [
    [{ id: 'b', room_number: '102', available: true }],
    [
      { id: 'a', room_number: '12', available: true },
      { id: 'b', room_number: '102', available: true },
    ],
  ];
  const grid = buildAvailabilityGrid(days, perDay, []);
  // Numeric-aware Turkish sort: "12" before "102".
  assert.deepEqual(grid.rooms.map((r) => r.room_number), ['12', '102']);
  assert.deepEqual(grid.days, days);
});

test('buildAvailabilityGrid: an explicit block marks a free cell blocked', () => {
  const days = buildDayList('2026-06-10', 3);
  const perDay: GridRoomInput[][] = days.map(() => [
    { id: 'r1', room_number: '101', available: true },
  ]);
  const blocks: GridBlockInput[] = [
    { room_id: 'r1', start_date: '2026-06-11', end_date: '2026-06-12' },
  ];
  const grid = buildAvailabilityGrid(days, perDay, blocks);
  const r1 = grid.rooms.find((r) => r.id === 'r1')!;
  assert.equal(r1.cells['2026-06-10'], 'free'); // before block
  assert.equal(r1.cells['2026-06-11'], 'blocked'); // inside block
  assert.equal(r1.cells['2026-06-12'], 'free'); // end-exclusive -> still free
});

test('buildAvailabilityGrid: occupied beats an overlapping block (no downgrade)', () => {
  const days = buildDayList('2026-06-10', 1);
  const perDay: GridRoomInput[][] = [
    [{ id: 'r1', room_number: '101', available: false, reason: 'booked' }],
  ];
  const blocks: GridBlockInput[] = [
    { room_id: 'r1', start_date: '2026-06-10', end_date: '2026-06-11' },
  ];
  const grid = buildAvailabilityGrid(days, perDay, blocks);
  assert.equal(grid.rooms[0].cells['2026-06-10'], 'occupied');
});

test('buildAvailabilityGrid: blocked beats free precedence', () => {
  const days = buildDayList('2026-06-10', 1);
  const perDay: GridRoomInput[][] = [
    [{ id: 'r1', room_number: '101', available: true }],
  ];
  const blocks: GridBlockInput[] = [
    { room_id: 'r1', start_date: '2026-06-10', end_date: '2026-06-11' },
  ];
  const grid = buildAvailabilityGrid(days, perDay, blocks);
  assert.equal(grid.rooms[0].cells['2026-06-10'], 'blocked');
});

test('buildAvailabilityGrid: allow_sell block is ignored, cell stays free', () => {
  const days = buildDayList('2026-06-10', 1);
  const perDay: GridRoomInput[][] = [
    [{ id: 'r1', room_number: '101', available: true }],
  ];
  const blocks: GridBlockInput[] = [
    {
      room_id: 'r1',
      start_date: '2026-06-10',
      end_date: '2026-06-11',
      allow_sell: true,
    },
  ];
  const grid = buildAvailabilityGrid(days, perDay, blocks);
  assert.equal(grid.rooms[0].cells['2026-06-10'], 'free');
});

test('buildAvailabilityGrid: a block for an unknown room is ignored', () => {
  const days = buildDayList('2026-06-10', 1);
  const perDay: GridRoomInput[][] = [
    [{ id: 'r1', room_number: '101', available: true }],
  ];
  const blocks: GridBlockInput[] = [
    { room_id: 'ghost', start_date: '2026-06-10', end_date: '2026-06-11' },
    { start_date: '2026-06-10', end_date: '2026-06-11' }, // no room_id
  ];
  const grid = buildAvailabilityGrid(days, perDay, blocks);
  assert.equal(grid.rooms.length, 1);
  assert.equal(grid.rooms[0].cells['2026-06-10'], 'free');
});

test('buildAvailabilityGrid: OOO room status renders blocked across the span', () => {
  const days = buildDayList('2026-06-10', 2);
  const perDay: GridRoomInput[][] = days.map(() => [
    { id: 'r1', room_number: '101', status: 'out_of_order', available: true },
  ]);
  const grid = buildAvailabilityGrid(days, perDay, []);
  assert.equal(grid.rooms[0].cells['2026-06-10'], 'blocked');
  assert.equal(grid.rooms[0].cells['2026-06-11'], 'blocked');
});

test('buildAvailabilityGrid: room_number falls back to id when missing', () => {
  const days = buildDayList('2026-06-10', 1);
  const perDay: GridRoomInput[][] = [[{ id: 'r1', available: true }]];
  const grid = buildAvailabilityGrid(days, perDay, []);
  assert.equal(grid.rooms[0].room_number, 'r1');
});
