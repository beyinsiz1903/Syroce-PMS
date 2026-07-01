// Unit coverage for the "change room" panel availability logic. Runs in plain
// Node via the built-in test runner (see `yarn test:unit` / tsconfig.unit.json)
// — no render harness, no extra dependencies. Guards against a future
// regression (e.g. offering every room, or a date-conversion bug) silently
// allowing a double-booking.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { isoDateOnly, filterAvailableRooms, roomPanelView } from '../availabilityFilters';

// ── isoDateOnly: normalise the reservation dates for the availability query ──
test('isoDateOnly passes through a plain YYYY-MM-DD date', () => {
  assert.equal(isoDateOnly('2026-06-10'), '2026-06-10');
});

test('isoDateOnly trims an ISO datetime down to the calendar day', () => {
  assert.equal(isoDateOnly('2026-06-10T14:30:00Z'), '2026-06-10');
  assert.equal(isoDateOnly('2026-06-10T00:00:00.000Z'), '2026-06-10');
  // The date prefix wins regardless of the runner timezone (no off-by-one).
  const prevTZ = process.env.TZ;
  for (const tz of ['UTC', 'America/Los_Angeles', 'Pacific/Kiritimati']) {
    process.env.TZ = tz;
    assert.equal(isoDateOnly('2026-06-10T23:59:59Z'), '2026-06-10', `TZ=${tz}`);
  }
  process.env.TZ = prevTZ;
});

test('isoDateOnly returns undefined for blank / unparseable input', () => {
  assert.equal(isoDateOnly(undefined), undefined);
  assert.equal(isoDateOnly(''), undefined);
  assert.equal(isoDateOnly('not-a-date'), undefined);
  assert.equal(isoDateOnly('hello world'), undefined);
});

// ── filterAvailableRooms: only available === true survives ──────────────────
test('filterAvailableRooms keeps only rooms flagged available === true', () => {
  const rooms = [
    { id: 'a', available: true },
    { id: 'b', available: false },
    { id: 'c', available: undefined },
    { id: 'd' }, // missing flag
    { id: 'e', available: true },
  ];
  assert.deepEqual(
    filterAvailableRooms(rooms).map((r) => r.id),
    ['a', 'e'],
  );
});

test('filterAvailableRooms is strict — truthy non-true values are excluded', () => {
  // Defends against a regression where `available` becomes a string/number and
  // a loose check would let a booked room through.
  const rooms = [
    { id: 'a', available: 'true' as unknown as boolean },
    { id: 'b', available: 1 as unknown as boolean },
    { id: 'c', available: true },
  ];
  assert.deepEqual(
    filterAvailableRooms(rooms).map((r) => r.id),
    ['c'],
  );
});

// ── roomPanelView: the loading / empty / list state machine ─────────────────
test('roomPanelView reports loading while the query is in flight', () => {
  assert.deepEqual(roomPanelView([], true), { kind: 'loading' });
  // Loading wins even if rooms are already present (stale list mid-refetch).
  assert.deepEqual(roomPanelView([{ id: 'a', available: true }], true), {
    kind: 'loading',
  });
});

test('roomPanelView reports empty when no room is available', () => {
  assert.deepEqual(roomPanelView([], false), { kind: 'empty' });
  // A list of only-unavailable rooms still renders the empty state — never the
  // booked rooms.
  assert.deepEqual(
    roomPanelView([{ id: 'a', available: false }, { id: 'b' }], false),
    { kind: 'empty' },
  );
});

test('roomPanelView lists ONLY the available rooms', () => {
  const view = roomPanelView(
    [
      { id: 'free-1', available: true },
      { id: 'booked', available: false },
      { id: 'free-2', available: true },
      { id: 'unknown' },
    ],
    false,
  );
  assert.equal(view.kind, 'list');
  if (view.kind === 'list') {
    assert.deepEqual(
      view.rooms.map((r) => r.id),
      ['free-1', 'free-2'],
    );
  }
});
