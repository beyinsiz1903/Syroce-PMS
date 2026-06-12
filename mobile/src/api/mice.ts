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

// ── Sales & Catering CRM (read-only) ───────────────────────────────────────
// Accounts mirror backend/routers/mice.py (GET /api/mice/accounts, auth only);
// opportunities mirror backend/routers/sales_catering.py
// (GET /api/mice/sales/opportunities, auth only). Writes stay gated by
// require_op("manage_sales") on the backend and are NOT exposed here.

export type MiceAccount = {
  id: string;
  name?: string;
  legal_name?: string | null;
  tax_no?: string | null;
  email?: string | null;
  city?: string | null;
  industry?: string | null;
  credit_limit?: number;
  payment_terms_days?: number;
  active?: boolean;
};

export type MiceOpportunity = {
  id: string;
  title?: string;
  account_id?: string | null;
  event_type?: string | null;
  stage?: string;
  estimated_value?: number;
  currency?: string;
  probability?: number;
  expected_start?: string | null;
  expected_end?: string | null;
  pax?: number;
  created_at?: string;
};

// GET /api/mice/accounts → { accounts: [...] }
export async function listMiceAccounts(): Promise<MiceAccount[]> {
  const res = await api.get<{ accounts?: MiceAccount[] }>('/api/mice/accounts');
  return res?.accounts ?? [];
}

// GET /api/mice/sales/opportunities?stage=&account_id=&limit=
export async function listMiceOpportunities(params?: {
  stage?: string;
  account_id?: string;
  limit?: number;
}): Promise<MiceOpportunity[]> {
  const res = await api.get<{ opportunities?: MiceOpportunity[] }>(
    '/api/mice/sales/opportunities',
    params,
  );
  return res?.opportunities ?? [];
}

// ── Groups / Blocks & Corporate Contracts (read-only) ──────────────────────
// Group reservations mirror backend/domains/pms/groups_router.py
// (GET /api/group-reservations), group blocks (GET /api/groups/blocks) and
// corporate contracts (GET /api/corporate/contracts) all require auth only on
// the backend. Writes (create-block, assign-rooms, release) stay gated by
// require_module_v101("frontdesk") and are NOT exposed here.

export type GroupReservation = {
  id: string;
  group_name?: string;
  group_type?: string;
  contact_person?: string | null;
  check_in_date?: string;
  check_out_date?: string;
  total_rooms?: number;
  rooms_assigned?: number;
  status?: string;
};

export type GroupBlock = {
  id: string;
  group_name?: string;
  organization?: string;
  contact_name?: string | null;
  check_in?: string;
  check_out?: string;
  total_rooms?: number;
  rooms_picked_up?: number;
  room_type?: string;
  group_rate?: number;
  status?: string;
};

export type CorporateContract = {
  id: string;
  company_name?: string;
  contract_type?: string;
  start_date?: string;
  end_date?: string;
  room_nights_committed?: number;
  room_nights_used?: number;
  contracted_rate?: number;
  discount_percentage?: number;
  contact_person?: string | null;
  status?: string;
  days_until_expiry?: number;
};

// GET /api/group-reservations → { groups: [...] }
export async function listGroupReservations(): Promise<GroupReservation[]> {
  const res = await api.get<{ groups?: GroupReservation[] }>('/api/group-reservations');
  return res?.groups ?? [];
}

// GET /api/groups/blocks?status= → { blocks: [...] }
export async function listGroupBlocks(params?: {
  status?: string;
}): Promise<GroupBlock[]> {
  const res = await api.get<{ blocks?: GroupBlock[] }>('/api/groups/blocks', params);
  return res?.blocks ?? [];
}

// GET /api/corporate/contracts?status= → { contracts: [...] }
export async function listCorporateContracts(params?: {
  status?: string;
}): Promise<CorporateContract[]> {
  const res = await api.get<{ contracts?: CorporateContract[] }>(
    '/api/corporate/contracts',
    params,
  );
  return res?.contracts ?? [];
}
