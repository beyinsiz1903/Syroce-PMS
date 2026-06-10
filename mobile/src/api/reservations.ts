import { api } from './client';

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
  try {
    return await api.get<ReservationDetailsEnhanced>(
      `/api/reservations/${encodeURIComponent(id)}/details-enhanced`,
    );
  } catch {
    return null;
  }
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
  try {
    return await api.get<ReservationOtaDetails>(
      `/api/reservations/${encodeURIComponent(id)}/ota-details`,
    );
  } catch {
    return null;
  }
}
