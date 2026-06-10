import { api } from './client';

// MICE / Events API client — read-focused mirror of backend/routers/mice.py.
// Reads are open to any authenticated user server-side; writes (not used here)
// stay gated by `require_mice_ops` / `require_catalog` on the backend.

export type MiceSpace = {
  id: string;
  name: string;
  location?: string;
  area_m2?: number;
  capacity_theatre?: number;
  capacity_classroom?: number;
  capacity_banquet?: number;
  capacity_cocktail?: number;
  capacity_u_shape?: number;
  capacity_boardroom?: number;
  hourly_rate?: number;
  daily_rate?: number;
  currency?: string;
  amenities?: string[];
  active?: boolean;
};

export type MiceResourceLine = {
  name?: string;
  type?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
};

export type MiceSpaceBooking = {
  space_id?: string;
  starts_at?: string;
  ends_at?: string;
  setup_style?: string;
  expected_pax?: number;
};

export type MiceTotals = {
  grand_total?: number;
  subtotal?: number;
  tax?: number;
  currency?: string;
};

export type MiceEvent = {
  id: string;
  name?: string;
  client_name?: string;
  client_email?: string | null;
  client_phone?: string | null;
  organizer_user?: string | null;
  event_type?: string;
  status?: string;
  expected_pax?: number;
  start_date?: string;
  end_date?: string;
  notes?: string | null;
  space_bookings?: MiceSpaceBooking[];
  resources?: MiceResourceLine[];
  totals?: MiceTotals;
};

// GET /api/mice/events?status=&date_from=&date_to=
export async function listMiceEvents(params?: {
  status?: string;
  date_from?: string;
  date_to?: string;
}): Promise<MiceEvent[]> {
  const res = await api.get<{ events?: MiceEvent[] }>('/api/mice/events', params);
  return res?.events ?? [];
}

// GET /api/mice/events/{id}
export async function getMiceEvent(eventId: string): Promise<MiceEvent> {
  return api.get<MiceEvent>(`/api/mice/events/${eventId}`);
}

// GET /api/mice/spaces
export async function listMiceSpaces(): Promise<MiceSpace[]> {
  const res = await api.get<{ spaces?: MiceSpace[] }>('/api/mice/spaces');
  return res?.spaces ?? [];
}
