import { api } from './client';
import type { Reservation } from './reservations';
import { loadCalendarReservationPages } from '../utils/calendarData';

// GET /api/pms/bookings applies tenant-scoped overlap filtering server-side:
// check_out > start_date and check_in < end_date (checkout is exclusive).
// Do not use reservations/search here: its unfiltered recent-50 result cannot
// establish whether a room is free within the visible calendar window.
export async function getCalendarReservations(
  startDate: string,
  endExclusive: string,
): Promise<Reservation[]> {
  return loadCalendarReservationPages<Reservation>(
    (params) => api.get<unknown>('/api/pms/bookings', params),
    startDate,
    endExclusive,
  );
}
