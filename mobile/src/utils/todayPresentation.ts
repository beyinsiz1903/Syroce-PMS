import { finiteMoney, reservationAmountLabel, reservationCurrency } from './reservationPresentation';

type TodayBookingLike = {
  id: string;
  guest_name?: string;
  check_in?: string;
  check_out?: string;
};

/** Keep the server balance in its own currency; never convert or assume TRY. */
export function todayBookingBalance(booking: { balance?: unknown; currency?: unknown }): {
  amount: number;
  currency?: string;
  label: string;
} | null {
  const amount = finiteMoney(booking.balance);
  if (amount === undefined || amount <= 0) return null;
  const currency = reservationCurrency(booking.currency);
  return { amount, currency, label: reservationAmountLabel(amount, currency) };
}

/** Calendar dates belong to the operator's day; UTC can still be yesterday. */
export function localDayISO(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** A failed request or an obsolete wrapped cache is not an empty list. */
export function todayCountLabel(data: unknown, unavailable: boolean): string {
  return unavailable || !Array.isArray(data) ? '—' : String(data.length);
}

export type TodayOccupancy = { percentage: number; occupied: number; total: number };

/** Executive metrics may be omitted by RBAC; never infer them from guest counts. */
export function todayOccupancy(data: unknown, unavailable = false): TodayOccupancy | null {
  if (unavailable || !data || typeof data !== 'object') return null;
  const digest = data as Record<string, unknown>;
  const percentage = digest.occupancy_pct;
  const occupied = digest.occupied_rooms;
  const total = digest.total_rooms;
  if (typeof percentage !== 'number' || !Number.isFinite(percentage) || percentage < 0 || percentage > 100
    || typeof occupied !== 'number' || !Number.isInteger(occupied) || occupied < 0
    || typeof total !== 'number' || !Number.isInteger(total) || total <= 0 || occupied > total) return null;
  // The API rounds to one decimal. A materially different ratio is not a
  // verified occupancy snapshot, even when each field is individually numeric.
  if (Math.abs(percentage - occupied / total * 100) > 0.1) return null;
  return { percentage, occupied, total };
}

function bookingDateTime(value: unknown): Date | null {
  // A date-only booking says nothing about the guest's expected arrival hour.
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value)) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

export function todayBookingTime(value: unknown): string | null {
  const date = bookingDateTime(value);
  return date ? date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : null;
}

/** Put known booking times first without manufacturing times for date-only stays. */
export function sortTodayBookings<T extends TodayBookingLike>(
  data: unknown,
  field: 'check_in' | 'check_out',
): T[] {
  if (!Array.isArray(data)) return [];
  return data
    .filter((booking): booking is T => !!booking && typeof booking.id === 'string')
    .slice()
    .sort((a, b) => {
      const aTime = bookingDateTime(a[field])?.getTime() ?? Infinity;
      const bTime = bookingDateTime(b[field])?.getTime() ?? Infinity;
      if (aTime !== bTime) return aTime < bTime ? -1 : 1;
      return String(a.guest_name || '').localeCompare(String(b.guest_name || ''), 'tr-TR');
    });
}

export function countLocalWalkIns(data: unknown, today = localDayISO()): number {
  if (!Array.isArray(data)) return 0;
  return data.filter((booking) => {
    if (!booking || String(booking.source ?? '').toLowerCase() !== 'walk_in') return false;
    if (typeof booking.check_in !== 'string') return false;
    const dateTime = bookingDateTime(booking.check_in);
    const day = dateTime ? localDayISO(dateTime) : booking.check_in;
    return day === today;
  }).length;
}
