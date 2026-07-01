/**
 * Helper to detect and unpack the structured 409 conflict response that
 * the backend returns from booking-create endpoints (quick-booking,
 * /pms/bookings, /pms/bookings/multi-room). Shape:
 *
 *   detail: {
 *     message: string,
 *     conflicting_booking_id: string|null,
 *     conflict_type: string,
 *     conflict_window: { room_id, check_in, check_out }
 *   }
 *
 * Older clients still receive a usable `message`, so callers can fall back
 * to a plain toast when this returns null.
 */
export function parseBookingConflict(error) {
  const status = error?.response?.status;
  if (status !== 409) return null;
  const detail = error?.response?.data?.detail;
  if (!detail || typeof detail !== 'object') return null;
  if (!detail.conflict_window && !detail.conflicting_booking_id) return null;
  return {
    message: detail.message || 'Bu oda istenen tarihlerde zaten dolu.',
    conflictingBookingId: detail.conflicting_booking_id || null,
    conflictType: detail.conflict_type || 'booking',
    conflictWindow: detail.conflict_window || null,
  };
}
