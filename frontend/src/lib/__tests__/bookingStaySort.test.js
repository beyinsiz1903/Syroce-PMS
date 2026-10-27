import { describe, expect, it } from 'vitest';
import { sortBookingsByStay } from '../bookingStaySort';

const stay = (id, check_in, check_out) => ({ id, check_in, check_out });
const ids = rows => rows.map(row => row.id);
const rows = [
  stay('far-2042', '2042-09-27', '2042-09-29'),
  stay('tomorrow', '2026-10-27', '2026-10-29'),
  stay('old', '2020-01-01', '2020-01-02'),
  stay('in-house', '2026-10-25', '2026-10-30'),
  stay('recent', '2026-10-23', '2026-10-24'),
];

describe('stay proximity to the PMS business day', () => {
  it('places current and near stays first without mutating full history', () => {
    expect(ids(sortBookingsByStay(rows, '2026-10-26'))).toEqual(['in-house', 'tomorrow', 'recent', 'old', 'far-2042']);
    expect(rows[0].id).toBe('far-2042');
  });

  it('offers farthest first and recomputes on a business-day change', () => {
    expect(ids(sortBookingsByStay(rows, '2026-10-26', 'farthest'))).toEqual(['far-2042', 'old', 'recent', 'tomorrow', 'in-house']);
    expect(sortBookingsByStay(rows, '2042-09-27')[0].id).toBe('far-2042');
  });

  it('uses calendar days rather than timezone shifts, with deterministic ties', () => {
    const ties = [stay('b', '2026-10-26T23:30:00-12:00'), stay('a', '2026-10-26T01:00:00+14:00')];
    expect(ids(sortBookingsByStay(ties, '2026-10-26'))).toEqual(['a', 'b']);
  });

  it('keeps malformed/missing dates last in either direction', () => {
    const invalid = [stay('bad', '2026-02-30'), stay('missing'), stay('valid', '2026-10-26')];
    for (const order of ['nearest', 'farthest']) {
      expect(ids(sortBookingsByStay(invalid, '2026-10-26', order))).toEqual(['valid', 'bad', 'missing']);
    }
  });

  it('ignores invalid checkout ranges and falls back to check-in', () => {
    expect(ids(sortBookingsByStay([stay('later', '2026-11-01', '2026-10-26'), stay('near', '2026-10-27')], '2026-10-26'))).toEqual(['near', 'later']);
  });

  it('falls back to chronological order, never the device clock, before business day loads', () => {
    expect(ids(sortBookingsByStay(rows, null))).toEqual(['old', 'recent', 'in-house', 'tomorrow', 'far-2042']);
    expect(sortBookingsByStay([], '2026-10-26')).toEqual([]);
  });
});
