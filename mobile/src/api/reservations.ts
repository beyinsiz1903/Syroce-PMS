import { api, apiRequest } from './client';
import type { Booking } from './bookings';
import type { Folio, FolioCharge, FolioPayment } from './folio';

// Mirrors the booking documents returned by GET /api/reservations/search.
// The backend enriches each row with room_number/room_type and the owning
// guest's phone/email (tenant-scoped) — no extra fetch is needed for the list.
export type Reservation = {
  id: string;
  guest_id?: string;
  guest_name?: string;
  booking_number?: string;
  room_id?: string;
  room_number?: string;
  room_type?: string;
  status?: string;
  check_in?: string;
  check_out?: string;
  total_amount?: number;
  paid_amount?: number;
  balance?: number;
  base_rate?: number;
  rate_type?: string;
  vip_status?: boolean;
  guest_phone?: string;
  guest_email?: string;
  special_requests?: string;
  ota_channel?: string;
  currency?: string;
};

export type ReservationSearchParams = {
  query?: string;
  status?: string;
  check_in?: string;
  check_out?: string;
  phone?: string;
  email?: string;
};

type SearchResponse = {
  bookings?: Reservation[];
  count?: number;
};

// GET /api/reservations/search — guest name / booking no / phone / email /
// date-range / status. Returns recent 50 (sorted by check_in desc) when no
// filters are supplied.
export async function searchReservations(
  params: ReservationSearchParams = {},
): Promise<Reservation[]> {
  const res = await api.get<SearchResponse>('/api/reservations/search', {
    query: params.query || undefined,
    status: params.status || undefined,
    check_in: params.check_in || undefined,
    check_out: params.check_out || undefined,
    phone: params.phone || undefined,
    email: params.email || undefined,
  });
  return Array.isArray(res?.bookings) ? res.bookings : [];
}

export type RateBreakdown = {
  base_rate?: number;
  total_amount?: number;
  rate_type?: string;
  market_segment?: string;
};

export type CancellationPolicy = {
  type?: string;
  [k: string]: unknown;
};

export type CommissionInfo = {
  ota_channel?: string;
  ota_confirmation?: string;
  commission_pct?: number;
  commission_amount?: number;
  gross_revenue?: number;
  net_revenue?: number;
  payment_model?: string;
};

export type ReservationDetailsEnhanced = {
  booking_id: string;
  status?: string;
  cancellation_policy?: CancellationPolicy;
  commission?: CommissionInfo | null;
  rate_breakdown?: RateBreakdown;
};

// GET /api/reservations/{id}/details-enhanced
export async function getReservationDetailsEnhanced(
  id: string,
): Promise<ReservationDetailsEnhanced | null> {
  return api.get<ReservationDetailsEnhanced>(
    `/api/reservations/${encodeURIComponent(id)}/details-enhanced`,
  );
}

export type ExtraCharge = {
  id?: string;
  charge_name?: string;
  charge_amount?: number;
  charge_date?: string;
  notes?: string | null;
};

export type RelatedBooking = {
  booking_id?: string;
  room_number?: string;
  guest_name?: string;
};

export type MultiRoomInfo = {
  group_name?: string;
  total_rooms?: number;
  related_bookings?: RelatedBooking[];
};

export type ReservationOtaDetails = {
  booking_id: string;
  special_requests?: string;
  adults?: number | null;
  children?: number | null;
  remarks?: string;
  source_of_booking?: string;
  ota_channel?: string | null;
  ota_confirmation?: string | null;
  extra_charges?: ExtraCharge[];
  multi_room_info?: MultiRoomInfo | null;
  commission_pct?: number | null;
  payment_model?: string | null;
};

// GET /api/reservations/{id}/ota-details
export async function getReservationOtaDetails(
  id: string,
): Promise<ReservationOtaDetails | null> {
  return api.get<ReservationOtaDetails>(
    `/api/reservations/${encodeURIComponent(id)}/ota-details`,
  );
}

// Existing web reservation-detail contract. Unlike the operational folio read,
// this carries actual folio identities, the full stay's server-calculated amount
// due (including unposted nights), currency, and the historical read-only flag.
export type ReservationFullDetail = {
  booking: Booking;
  guest?: { name?: string; first_name?: string; last_name?: string; phone?: string; email?: string } | null;
  room?: { room_number?: string; room_type?: string } | null;
  company?: { name?: string; company_name?: string } | null;
  folios?: Folio[];
  charges?: FolioCharge[];
  payments?: FolioPayment[];
  summary?: { gross_total?: number; reservation_total_due?: number; pricing_reconciliation_required?: boolean };
  read_only?: boolean;
};

function pickFields<T extends object, K extends keyof T>(value: T, keys: readonly K[]): Pick<T, K> {
  const selected = {} as Pick<T, K>;
  for (const key of keys) selected[key] = value[key];
  return selected;
}

export async function getReservationFullDetail(id: string): Promise<ReservationFullDetail | null> {
  const res = await api.get<ReservationFullDetail>(`/api/pms/reservations/${encodeURIComponent(id)}/full-detail`);
  if (res?.booking?.id !== id) return null;
  // The broad web endpoint also returns identity documents, communication logs
  // and guest links. Keep only this screen's fields in the persisted query cache.
  return {
    booking: pickFields(res.booking, ['id', 'guest_name', 'booking_number', 'room_number', 'room_type', 'check_in', 'check_out', 'status', 'total_amount', 'balance', 'collected_amount', 'currency', 'adults', 'children', 'guest_phone', 'guest_email', 'special_requests', 'channel', 'source_channel', 'booking_source', 'source', 'ota_channel', 'agency_id', 'agency_name', 'company_id', 'payment_model']),
    guest: res.guest ? pickFields(res.guest, ['name', 'first_name', 'last_name', 'phone', 'email']) : res.guest,
    room: res.room ? pickFields(res.room, ['room_number', 'room_type']) : res.room,
    company: res.company ? pickFields(res.company, ['name', 'company_name']) : res.company,
    folios: Array.isArray(res.folios) ? res.folios.map((folio) => pickFields(folio, ['id', 'folio_number', 'folio_type', 'payor_type', 'status', 'currency'])) : undefined,
    charges: Array.isArray(res.charges) ? res.charges.map((charge) => pickFields(charge, ['id', 'folio_id', 'description', 'charge_category', 'amount', 'total', 'currency', 'voided'])) : undefined,
    payments: Array.isArray(res.payments) ? res.payments.map((payment) => pickFields(payment, ['id', 'folio_id', 'amount', 'currency', 'method', 'status', 'payment_type', 'voided', 'processed_at', 'reference'])) : undefined,
    summary: res.summary ? pickFields(res.summary, ['gross_total', 'reservation_total_due', 'pricing_reconciliation_required']) : undefined,
    read_only: res.read_only,
  };
}

// ---------------------------------------------------------------------------
// Mutations — reuse the same endpoints the web app calls. RBAC / tenant scope
// is enforced server-side; the mobile UI never short-circuits authorization.
// ---------------------------------------------------------------------------

export type ReservationUpdate = {
  check_in?: string;
  check_out?: string;
  total_amount?: number;
  room_id?: string;
  status?: string;
  adults?: number;
  children?: number;
  guests_count?: number;
  special_requests?: string;
  rate_type?: string;
  market_segment?: string;
};

// PUT /api/pms/bookings/{id} — edit dates / fields. Requires `pms` module.
// A status transition to "cancelled" releases inventory server-side.
export async function updateReservation(
  id: string,
  body: ReservationUpdate,
): Promise<unknown> {
  return api.put(`/api/pms/bookings/${encodeURIComponent(id)}`, body);
}

// Cancel = update status. The backend's UpdateReservationService detects the
// transition and frees the booked nights + emits EV_RESERVATION_CANCELLED.
export async function cancelReservation(id: string): Promise<unknown> {
  return updateReservation(id, { status: 'cancelled' });
}

// POST /api/reservations/rate-override-panel — booking_id / new_rate /
// override_reason are query params. Requires the `override_rate` permission
// (admin / super_admin / supervisor); other roles get a 403 server-side.
export async function overrideRate(
  id: string,
  newRate: number,
  reason: string,
): Promise<unknown> {
  return apiRequest('/api/reservations/rate-override-panel', {
    method: 'POST',
    query: {
      booking_id: id,
      new_rate: newRate,
      override_reason: reason,
    },
  });
}
