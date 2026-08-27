import {
  RESERVATION_EDIT_LOCK_HEADER,
  RESERVATION_EDIT_LOCK_HEARTBEAT_SECONDS,
  RESERVATION_EDIT_LOCK_LEASE_SECONDS,
  reservationIdFromFullDetailUrl,
  reservationIdFromProtectedMutation,
} from '../reservationEditLockManager';

describe('reservationEditLockManager contract', () => {
  it('pins the server lease and heartbeat cadence', () => {
    expect(RESERVATION_EDIT_LOCK_LEASE_SECONDS).toBe(120);
    expect(RESERVATION_EDIT_LOCK_HEARTBEAT_SECONDS).toBe(30);
    expect(RESERVATION_EDIT_LOCK_HEADER).toBe('X-Reservation-Lock-ID');
  });

  it('detects the full-detail view that must acquire a per-view lock', () => {
    expect(
      reservationIdFromFullDetailUrl('/pms/reservations/booking-a/full-detail'),
    ).toBe('booking-a');
    expect(
      reservationIdFromFullDetailUrl('/api/pms/reservations/booking-b/full-detail?x=1'),
    ).toBe('booking-b');
    expect(reservationIdFromFullDetailUrl('/pms/reservations')).toBeNull();
  });

  it('requires lock propagation on reservation-detail mutations', () => {
    expect(
      reservationIdFromProtectedMutation('/pms/reservations/booking-a/notes', 'post'),
    ).toBe('booking-a');
    expect(
      reservationIdFromProtectedMutation('/api/pms/reservations/booking-a/vip-status', 'PUT'),
    ).toBe('booking-a');
    expect(
      reservationIdFromProtectedMutation('/frontdesk/checkin/booking-a?force_clean=true', 'post'),
    ).toBe('booking-a');
    expect(
      reservationIdFromProtectedMutation('/api/frontdesk/checkout/booking-a', 'POST'),
    ).toBe('booking-a');
  });

  it('does not gate reads or recursively gate lock-management endpoints', () => {
    expect(
      reservationIdFromProtectedMutation('/pms/reservations/booking-a/full-detail', 'get'),
    ).toBeNull();
    expect(
      reservationIdFromProtectedMutation('/pms/reservations/booking-a/edit-lock/acquire', 'post'),
    ).toBeNull();
    expect(
      reservationIdFromProtectedMutation('/pms/reservations/booking-a/edit-lock/heartbeat', 'post'),
    ).toBeNull();
  });
});
