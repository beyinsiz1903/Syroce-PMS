import type { CalReservation } from './reservationCalendar';

export const CALENDAR_PAGE_SIZE = 200;
export const CALENDAR_MAX_PAGES = 100;

export type CalendarPageParams = {
  start_date: string;
  end_date: string;
  limit: number;
  offset: number;
};

export type CalendarDataFailure = 'invalid_range' | 'invalid_page' | 'duplicate_booking' | 'page_limit';

export class CalendarDataError extends Error {
  readonly reason: CalendarDataFailure;

  constructor(reason: CalendarDataFailure) {
    super(reason === 'invalid_range'
      ? 'Takvim tarih aralığı geçersiz.'
      : 'Takvim verileri alınamadı. Yeniden deneyin.');
    this.name = 'CalendarDataError';
    this.reason = reason;
  }
}

function validCalendarDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function validBookingDate(value: unknown): value is string {
  if (typeof value !== 'string' || !validCalendarDate(value.slice(0, 10))) return false;
  if (value.length === 10) return true;
  return /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value) && Number.isFinite(new Date(value).getTime());
}

const DISPLAY_STRING_FIELDS = ['room_id', 'room_number', 'room_type', 'guest_name', 'status'] as const;

function validCalendarBooking(value: unknown): value is CalReservation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const booking = value as Record<string, unknown>;
  return typeof booking.id === 'string' && !!booking.id.trim()
    && validBookingDate(booking.check_in) && validBookingDate(booking.check_out)
    && booking.check_out.slice(0, 10) > booking.check_in.slice(0, 10)
    && DISPLAY_STRING_FIELDS.every((key) => booking[key] == null || typeof booking[key] === 'string');
}

/**
 * Load the entire overlapping window. An error never returns earlier pages:
 * incomplete inventory must not turn an occupied room into a free grid cell.
 * The filtered bookings endpoint returns raw arrays and honors limit/offset.
 */
export async function loadCalendarReservationPages<T extends CalReservation>(
  requestPage: (params: CalendarPageParams) => Promise<unknown>,
  startDate: string,
  endExclusive: string,
  options: { pageSize?: number; maxPages?: number } = {},
): Promise<T[]> {
  if (!validCalendarDate(startDate) || !validCalendarDate(endExclusive) || endExclusive <= startDate) {
    throw new CalendarDataError('invalid_range');
  }
  const pageSize = options.pageSize ?? CALENDAR_PAGE_SIZE;
  const maxPages = options.maxPages ?? CALENDAR_MAX_PAGES;
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 1000
    || !Number.isInteger(maxPages) || maxPages < 1 || maxPages > CALENDAR_MAX_PAGES) {
    throw new CalendarDataError('invalid_page');
  }

  const bookings: T[] = [];
  const seenIds = new Set<string>();
  for (let page = 0; page < maxPages; page += 1) {
    const data = await requestPage({
      start_date: startDate,
      end_date: endExclusive,
      limit: pageSize,
      offset: page * pageSize,
    });
    if (!Array.isArray(data) || data.length > pageSize || !data.every(validCalendarBooking)) {
      throw new CalendarDataError('invalid_page');
    }
    for (const booking of data) {
      if (seenIds.has(booking.id)) throw new CalendarDataError('duplicate_booking');
      seenIds.add(booking.id);
      bookings.push(booking as T);
    }
    // A full final page still needs the next request to prove completion.
    if (data.length < pageSize) return bookings;
  }
  throw new CalendarDataError('page_limit');
}

export type CalendarQueryState = {
  data: unknown;
  isPending: boolean;
  isError: boolean;
  isPlaceholderData?: boolean;
  fetchStatus?: 'fetching' | 'paused' | 'idle';
};

/** Offline data or a placeholder from another window cannot establish availability. */
export function calendarDataReady(online: boolean, queries: CalendarQueryState[]): boolean {
  return online && queries.length > 0 && queries.every((query) =>
    !query.isPending && !query.isError && !query.isPlaceholderData
    && query.fetchStatus !== 'paused' && query.fetchStatus !== 'fetching' && Array.isArray(query.data),
  );
}

export type CalendarRoomBlock = {
  id: string; room_id?: string; start_date?: string; end_date?: string | null;
  allow_sell?: boolean; status?: string;
};

// The existing blocks endpoint caps its result at 1000 without pagination.
// A capped or malformed result is not evidence that all other rooms are free.
export function verifiedRoomBlocks<T extends CalendarRoomBlock>(payload: unknown): T[] {
  const object = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown> : undefined;
  const rows = Array.isArray(payload) ? payload : Array.isArray(object?.blocks) ? object.blocks : object?.items;
  if (!Array.isArray(rows) || rows.length >= 1000
    || (object?.count !== undefined && object.count !== rows.length)) throw new CalendarDataError('invalid_page');
  const seen = new Set<string>();
  return rows.map((raw) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new CalendarDataError('invalid_page');
    const block = raw as Record<string, unknown>;
    if (typeof block.id !== 'string' || !block.id.trim() || seen.has(block.id)
      || typeof block.room_id !== 'string' || !block.room_id.trim()
      || (block.allow_sell != null && typeof block.allow_sell !== 'boolean')) throw new CalendarDataError('invalid_page');
    seen.add(block.id);
    const normalized = { ...block };
    for (const field of ['start_date', 'end_date']) {
      const value = block[field];
      if (value === undefined || value === null || value === '') continue; // legacy open boundaries
      if (!validBookingDate(value)) throw new CalendarDataError('invalid_page');
      normalized[field] = value.slice(0, 10);
    }
    if (normalized.start_date && normalized.end_date && String(normalized.end_date) < String(normalized.start_date)) {
      throw new CalendarDataError('invalid_page');
    }
    return normalized as T;
  });
}
