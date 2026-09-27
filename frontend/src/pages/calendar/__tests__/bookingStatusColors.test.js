import { describe, expect, it } from 'vitest';

import { applyBookingOperation, getBookingStatusColor } from '../calendarHelpers';

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

describe('applyBookingOperation', () => {
  const bookings = [
    { id: 'booking-a', status: 'confirmed' },
    { id: 'booking-b', status: 'confirmed' },
  ];

  it('updates check-in color state immediately without changing other bookings', () => {
    const result = applyBookingOperation(
      bookings,
      { bookingId: 'booking-a', operation: 'checked_in' },
      '2026-09-27T15:00:00.000Z',
    );

    expect(result[0]).toMatchObject({
      id: 'booking-a', status: 'checked_in', checked_in_at: '2026-09-27T15:00:00.000Z',
    });
    expect(result[1]).toBe(bookings[1]);
    expect(getBookingStatusColor(result[0]).bg).toBe('#16a34a');
  });

  it('updates check-out color state immediately', () => {
    const result = applyBookingOperation(
      [{ id: 'booking-a', status: 'checked_in' }],
      { bookingId: 'booking-a', operation: 'checked_out' },
      '2026-09-27T16:00:00.000Z',
    );

    expect(result[0]).toMatchObject({
      status: 'checked_out', checked_out_at: '2026-09-27T16:00:00.000Z',
    });
    expect(getBookingStatusColor(result[0]).bg).toBe('#dc2626');
  });
});
