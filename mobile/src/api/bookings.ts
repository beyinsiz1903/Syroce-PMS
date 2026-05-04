import { api } from './client';

export type Booking = {
  id: string;
  guest_id?: string;
  guest_name?: string;
  room_id?: string;
  room_number?: string;
  room_type?: string;
  status?: string;
  check_in?: string;
  check_out?: string;
  total_amount?: number;
  paid_amount?: number;
  balance?: number;
  vip_status?: boolean;
  special_requests?: string;
  no_show_risk?: number;
};

type BookingListResponse =
  | Booking[]
  | {
      arrivals?: Booking[];
      departures?: Booking[];
      bookings?: Booking[];
      items?: Booking[];
      data?: { arrivals?: Booking[]; departures?: Booking[] };
    };

type UnwrapKey =
  | 'arrivals'
  | 'departures'
  | 'bookings'
  | 'items'
  | 'data.arrivals'
  | 'data.departures';

function unwrap(res: BookingListResponse, keys: UnwrapKey[]): Booking[] {
  if (Array.isArray(res)) return res;
  if (!res) return [];
  for (const k of keys) {
    if (k === 'data.arrivals') {
      const inner = (res as { data?: { arrivals?: Booking[] } }).data?.arrivals;
      if (Array.isArray(inner)) return inner;
      continue;
    }
    if (k === 'data.departures') {
      const inner = (res as { data?: { departures?: Booking[] } }).data?.departures;
      if (Array.isArray(inner)) return inner;
      continue;
    }
    const value = (res as Record<string, unknown>)[k];
    if (Array.isArray(value)) return value as Booking[];
  }
  return [];
}

// GET /api/arrivals/today (frontdesk_router.py)
export async function getTodayArrivals(): Promise<Booking[]> {
  const res = await api.get<BookingListResponse>('/api/arrivals/today');
  return unwrap(res, ['arrivals', 'bookings', 'items', 'data.arrivals']);
}

// GET /api/unified/today-departures (frontdesk_router.py)
export async function getTodayDepartures(): Promise<Booking[]> {
  try {
    const res = await api.get<BookingListResponse>('/api/unified/today-departures');
    return unwrap(res, ['departures', 'bookings', 'items', 'data.departures']);
  } catch {
    return [];
  }
}

export type NoShowRiskEntry = {
  booking_id: string;
  score: number;
  level: 'low' | 'medium' | 'high' | string;
  guest_name?: string;
  room_number?: string;
};

// POST /api/pms/no-show-risk/bulk  body: { booking_ids: [...] }
// Scores today's arrivals and returns medium/high risk entries enriched with arrival info.
export async function getNoShowRisk(): Promise<NoShowRiskEntry[]> {
  try {
    const arrivals = await getTodayArrivals();
    const ids = arrivals.map((a) => a.id).filter(Boolean);
    if (ids.length === 0) return [];
    const res = await api.post<{ results?: Record<string, { score: number; level: string }> }>(
      '/api/pms/no-show-risk/bulk',
      { booking_ids: ids },
    );
    const results = res?.results || {};
    const out: NoShowRiskEntry[] = [];
    for (const a of arrivals) {
      const r = results[a.id];
      if (!r) continue;
      if (r.level === 'medium' || r.level === 'high') {
        out.push({
          booking_id: a.id,
          score: r.score,
          level: r.level,
          guest_name: a.guest_name,
          room_number: a.room_number,
        });
      }
    }
    out.sort((x, y) => y.score - x.score);
    return out;
  } catch {
    return [];
  }
}

// GET /api/pms/bookings (pms_bookings.py)
export async function searchBookingByRoom(roomNumber: string): Promise<Booking[]> {
  try {
    const res = await api.get<BookingListResponse>('/api/pms/bookings', {
      room_number: roomNumber,
      status: 'checked_in',
    });
    return unwrap(res, ['bookings', 'items']);
  } catch {
    return [];
  }
}

// GET /api/pms/bookings?id=<id> (no per-id GET; use list filter as best-effort)
export async function getBooking(id: string): Promise<Booking | null> {
  try {
    const res = await api.get<BookingListResponse>('/api/pms/bookings', { id });
    const items = unwrap(res, ['bookings', 'items']);
    return items.find((b) => b.id === id) || items[0] || null;
  } catch {
    return null;
  }
}

// POST /api/frontdesk/checkin/{booking_id}
export async function checkin(bookingId: string): Promise<unknown> {
  return api.post(`/api/frontdesk/checkin/${bookingId}`, {});
}

// POST /api/frontdesk/assign-room  body: { booking_id, room_id }
export async function assignRoom(bookingId: string, roomId: string): Promise<unknown> {
  return api.post('/api/frontdesk/assign-room', {
    booking_id: bookingId,
    room_id: roomId,
  });
}

// POST /api/frontdesk/checkout/{booking_id}
export async function checkout(bookingId: string, force = false): Promise<unknown> {
  return api.post(
    `/api/frontdesk/checkout/${bookingId}?force=${force}&auto_close_folios=true`,
    {},
  );
}

export type WalkInPayload = {
  guest_name: string;
  room_id: string;
  nights?: number;
  rate_amount?: number;
  payment_method?: string;
  guest_phone?: string;
  guest_email?: string;
  id_number?: string;
};

// POST /api/frontdesk/v2/walk-in (frontdesk_router_v2.py)
export async function walkInQuick(payload: WalkInPayload): Promise<unknown> {
  return api.post('/api/frontdesk/v2/walk-in', {
    nights: 1,
    rate_amount: 0,
    payment_method: 'cash',
    ...payload,
  });
}
