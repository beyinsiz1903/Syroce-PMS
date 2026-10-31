import { describe, expect, it } from 'vitest';
import { formatHotelEventTimestamp, formatHotelEventTime, hotelEventDay, hotelEventEpoch } from '../hotelEventTime';

describe('hotel event instants, not calendar/service days', () => {
  it.each(['2026-10-31T16:34:54.123456', '2026-10-31T16:34:54Z', '2026-10-31 16:34:54', '2026-10-31T19:34:54+03:00', '2026-10-31T11:34:54-0500'])('renders %s in explicit Istanbul time once', value => {
    expect(formatHotelEventTimestamp(value)).toBe('31.10.2026 19:34:54');
    expect(formatHotelEventTime(value, { seconds: false })).toBe('19:34');
  });
  it('handles Date objects and midnight in the hotel, independent of process TZ', () => {
    const value = new Date('2026-10-31T22:05:06Z');
    expect(hotelEventDay(value)).toBe('2026-11-01');
    expect(formatHotelEventTimestamp(value, { seconds: false })).toBe('01.11.2026 01:05');
  });
  it.each([null, undefined, '', '2026-10-26', 'invalid', new Date('invalid')])('does not invent an event for %s', value => {
    expect(formatHotelEventTimestamp(value)).toBe('—');
    expect(formatHotelEventTime(value)).toBe('—');
    if (value !== undefined) expect(hotelEventDay(value)).toBe(''); // undefined explicitly selects the current hotel day.
    expect(hotelEventEpoch(value)).toBeNull();
  });
  it('sorts a legacy UTC event and an explicitly offset event by the same instant clock', () => {
    expect(hotelEventEpoch('2026-10-31T19:34:54+03:00')).toBe(hotelEventEpoch('2026-10-31T16:34:54'));
    expect(hotelEventEpoch('2026-10-31T16:35:00')).toBeGreaterThan(hotelEventEpoch('2026-10-31T19:34:54+03:00'));
  });
});
