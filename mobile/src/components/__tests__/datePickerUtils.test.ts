// Unit coverage for the <DatePicker> date math. Runs in plain Node via the
// built-in test runner (see `yarn test:unit` / tsconfig.unit.json) — no render
// harness, no extra dependencies. Guards against a future change silently
// breaking date selection on the reservations / availability filters.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMonthCells,
  daysInMonth,
  firstWeekdayIndex,
  isBeforeMin,
  isBeforeMinParts,
  parseISO,
  toISO,
  todayParts,
  todayShortcutISO,
} from '../datePickerUtils';

// ── ISO output is timezone-safe (no off-by-one day) ────────────────────────
test('toISO builds a zero-padded YYYY-MM-DD with 0-based month', () => {
  assert.equal(toISO(2026, 0, 1), '2026-01-01'); // January, day 1
  assert.equal(toISO(2026, 11, 31), '2026-12-31'); // December, day 31
  assert.equal(toISO(2026, 5, 9), '2026-06-09'); // single-digit padded
});

test('toISO does not shift the day across timezones', () => {
  // A naive `new Date(y, m, d).toISOString()` would roll back to the previous
  // day in any timezone west of UTC. toISO formats from the parts directly, so
  // the calendar day is always preserved regardless of the runner's TZ.
  const prevTZ = process.env.TZ;
  for (const tz of ['UTC', 'America/Los_Angeles', 'Pacific/Kiritimati']) {
    process.env.TZ = tz;
    assert.equal(toISO(2026, 0, 1), '2026-01-01', `TZ=${tz}`);
    assert.equal(toISO(2026, 2, 15), '2026-03-15', `TZ=${tz}`);
  }
  process.env.TZ = prevTZ;
});

test('parseISO round-trips with toISO and rejects junk', () => {
  const parts = parseISO('2026-06-09');
  assert.deepEqual(parts, { y: 2026, m: 5, d: 9 });
  assert.equal(parts && toISO(parts.y, parts.m, parts.d), '2026-06-09');

  // Empty / cleared value → null (no selection).
  assert.equal(parseISO(undefined), null);
  assert.equal(parseISO(''), null);
  // Malformed / out-of-range → null (not a thrown error, not a wrong date).
  assert.equal(parseISO('2026-6-9'), null);
  assert.equal(parseISO('2026-13-01'), null);
  assert.equal(parseISO('2026-00-10'), null);
  assert.equal(parseISO('not-a-date'), null);
});

// ── minimumDate disables earlier days ──────────────────────────────────────
test('isBeforeMin disables days strictly before the bound, inclusive of it', () => {
  const min = '2026-06-10';
  // Day before the bound → disabled.
  assert.equal(isBeforeMin(min, 2026, 5, 9), true);
  // The bound itself → enabled (inclusive lower bound).
  assert.equal(isBeforeMin(min, 2026, 5, 10), false);
  // Day after the bound → enabled.
  assert.equal(isBeforeMin(min, 2026, 5, 11), false);
  // Earlier month / year → disabled.
  assert.equal(isBeforeMin(min, 2026, 4, 30), true);
  assert.equal(isBeforeMin(min, 2025, 11, 31), true);
  // Later month / year → enabled.
  assert.equal(isBeforeMin(min, 2026, 6, 1), false);
  assert.equal(isBeforeMin(min, 2027, 0, 1), false);
});

test('isBeforeMin with no bound never disables', () => {
  assert.equal(isBeforeMin(undefined, 1990, 0, 1), false);
  assert.equal(isBeforeMin('', 1990, 0, 1), false);
  // A malformed bound parses to null → treated as "no bound".
  assert.equal(isBeforeMin('garbage', 1990, 0, 1), false);
  assert.equal(isBeforeMinParts(null, 1990, 0, 1), false);
});

// ── today shortcut works ───────────────────────────────────────────────────
test('todayShortcutISO returns today when no bound or today >= bound', () => {
  const today = { y: 2026, m: 5, d: 10 };
  assert.equal(todayShortcutISO(today), '2026-06-10');
  assert.equal(todayShortcutISO(today, '2026-06-01'), '2026-06-10');
  // Bound equals today → still selectable (inclusive).
  assert.equal(todayShortcutISO(today, '2026-06-10'), '2026-06-10');
});

test('todayShortcutISO returns null when today is before the bound', () => {
  const today = { y: 2026, m: 5, d: 10 };
  // Today is disabled by a future minimum → shortcut must not select it.
  assert.equal(todayShortcutISO(today, '2026-06-11'), null);
  assert.equal(todayShortcutISO(today, '2026-07-01'), null);
});

test('todayParts reads local Y/M/D from an injected date', () => {
  assert.deepEqual(todayParts(new Date(2026, 5, 9, 23, 59)), {
    y: 2026,
    m: 5,
    d: 9,
  });
});

// ── calendar grid math ─────────────────────────────────────────────────────
test('daysInMonth handles month lengths and leap years', () => {
  assert.equal(daysInMonth(2026, 0), 31); // Jan
  assert.equal(daysInMonth(2026, 1), 28); // Feb (non-leap)
  assert.equal(daysInMonth(2024, 1), 29); // Feb (leap)
  assert.equal(daysInMonth(2026, 3), 30); // Apr
});

test('firstWeekdayIndex is Monday-based (0=Mon .. 6=Sun)', () => {
  // 2026-06-01 is a Monday → index 0.
  assert.equal(firstWeekdayIndex(2026, 5), 0);
  // 2026-02-01 is a Sunday → index 6.
  assert.equal(firstWeekdayIndex(2026, 1), 6);
});

test('buildMonthCells pads leading blanks then lists each day', () => {
  // June 2026 starts on Monday (lead 0) and has 30 days.
  const june = buildMonthCells(2026, 5);
  assert.equal(june.length, 30);
  assert.equal(june[0], 1);
  assert.equal(june[29], 30);

  // February 2026 starts on Sunday (lead 6) and has 28 days.
  const feb = buildMonthCells(2026, 1);
  assert.equal(feb.length, 6 + 28);
  assert.deepEqual(feb.slice(0, 6), [null, null, null, null, null, null]);
  assert.equal(feb[6], 1);
  assert.equal(feb[feb.length - 1], 28);
});
