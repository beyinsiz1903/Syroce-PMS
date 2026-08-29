import { describe, expect, it } from 'vitest';

import { getBookingStatusColor } from '../calendarHelpers';

describe('reservation calendar lifecycle colors', () => {
  it('shows every pre-arrival lifecycle in blue regardless of date or channel', () => {
    const blue = { bg: '#2563eb', border: '#1d4ed8' };

    expect(getBookingStatusColor({ status: 'confirmed', check_out: '2020-01-01', channel: 'agoda' })).toEqual(blue);
    expect(getBookingStatusColor({ status: 'guaranteed', check_in: '2026-08-29', channel: 'expedia' })).toEqual(blue);
    expect(getBookingStatusColor({ status: 'pending', channel: 'direct' })).toEqual(blue);
  });

  it('shows checked-in reservations in green', () => {
    expect(getBookingStatusColor({ status: 'checked_in' })).toEqual({
      bg: '#16a34a',
      border: '#15803d',
    });
  });

  it('shows checked-out reservations in red', () => {
    expect(getBookingStatusColor({ status: 'checked_out' })).toEqual({
      bg: '#dc2626',
      border: '#b91c1c',
    });
  });
});
