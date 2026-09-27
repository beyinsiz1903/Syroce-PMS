import { describe, expect, it } from 'vitest';
import {
  formatCalendarMonthRange,
  formatRoomTypeLabel,
  normalizeRoomTypeKey,
} from '../CalendarGrid';

describe('calendar presentation normalization', () => {
  it('groups room types case-insensitively', () => {
    expect(normalizeRoomTypeKey('Standard')).toBe('standard');
    expect(normalizeRoomTypeKey(' standard ')).toBe('standard');
    expect(formatRoomTypeLabel('STANDARD')).toBe('Standard');
  });

  it('shows both months when the visible range crosses a month boundary', () => {
    expect(formatCalendarMonthRange([
      new Date('2026-09-24T00:00:00'),
      new Date('2026-10-07T00:00:00'),
    ])).toBe('EYLÜL — EKİM 2026');
  });

  it('shows both years when the visible range crosses a year boundary', () => {
    expect(formatCalendarMonthRange([
      new Date('2026-12-28T00:00:00'),
      new Date('2027-01-10T00:00:00'),
    ])).toBe('ARALIK 2026 — OCAK 2027');
  });
});
