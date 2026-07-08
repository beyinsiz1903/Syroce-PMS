import { api, apiRequest } from './client';

// POS / F&B API client — mirror of the backend POS endpoints
// (backend/domains/pms/pos_fnb_router/* and backend/domains/pms/mobile_router/pos.py).
// List reads only require auth; every write below is gated server-side by
// require_module("pos") (order open/close, table transfer) or require_op
// (folio post). The mobile `posAccess` entitlement mirrors MODULE_ROLES["pos"]
// so we only surface the action UI to users who could act — the backend still
// enforces every write. Order/transaction status semantics are NOT changed
// here: open = quick-order → pos_orders/pending; the lifecycle PUT only moves
// pending → preparing → ready → served/cancelled; folio post mirrors the
// backend create-order charge path. Nothing weakens the backend contract.

export type Outlet = {
  id: string;
  outlet_name?: string;
  name?: string;
  outlet_type?: string;
  location?: string;
  status?: string;
  today_transactions?: number;
};

export type MenuItem = {
  id: string;
  outlet_id?: string;
  item_name?: string;
  name?: string;
  category?: string;
  price?: number;
  status?: string;
};

export type ActiveOrder = {
  id: string;
  order_number?: string;
  status?: string;
  outlet_id?: string;
  outlet_name?: string;
  table_number?: string;
  room_number?: string;
  guest_name?: string;
  items_count?: number;
  total_amount?: number;
  // Tax-inclusive amount collected at close (close_order reads grand_total).
  // Absent on legacy docs; clients fall back to total_amount for display.
  grand_total?: number;
  time_elapsed_minutes?: number;
  is_delayed?: boolean;
  created_at?: string;
  notes?: string;
};

export type TableSlot = {
  id?: string;
  table_number?: string;
  seats?: number;
  status?: string;
  server_assigned?: string | null;
  current_bill?: number;
  guest_count?: number;
  duration_minutes?: number;
};

export type TableLayout = {
  outlet_id: string;
  total_tables: number;
  available: number;
  occupied: number;
  reserved: number;
  tables: TableSlot[];
};

export type OrderStatus = 'pending' | 'preparing' | 'ready' | 'served' | 'cancelled';

// GET /api/pos/outlets → { outlets, count }
export async function listOutlets(): Promise<Outlet[]> {
  const res = await api.get<{ outlets?: Outlet[] }>('/api/pos/outlets');
  return (res?.outlets ?? []).filter((o) => o.status !== 'inactive');
}

// GET /api/pos/menu-items?outlet_id=&category= → { menu_items, count }
export async function listMenuItems(params?: {
  outlet_id?: string;
  category?: string;
}): Promise<MenuItem[]> {
  const res = await api.get<{ menu_items?: MenuItem[] }>('/api/pos/menu-items', params);
  return (res?.menu_items ?? []).filter((m) => m.status !== 'inactive');
}

// GET /api/pos/mobile/active-orders?status=&outlet_id= → { orders, count, delayed_count }
export async function listActiveOrders(params?: {
  status?: string;
  outlet_id?: string;
}): Promise<{ orders: ActiveOrder[]; delayed_count: number }> {
  const res = await api.get<{ orders?: ActiveOrder[]; delayed_count?: number }>(
    '/api/pos/mobile/active-orders',
    params,
  );
  return { orders: res?.orders ?? [], delayed_count: res?.delayed_count ?? 0 };
}

// GET /api/pos/table-layout/{outlet_id}
export async function getTableLayout(outletId: string): Promise<TableLayout> {
  const res = await api.get<Partial<TableLayout>>(
    `/api/pos/table-layout/${encodeURIComponent(outletId)}`,
  );
  return {
    outlet_id: res?.outlet_id ?? outletId,
    total_tables: res?.total_tables ?? 0,
    available: res?.available ?? 0,
    occupied: res?.occupied ?? 0,
    reserved: res?.reserved ?? 0,
    tables: res?.tables ?? [],
  };
}

// POST /api/pos/mobile/quick-order — open a new order (pos_orders/pending).
// An optional `idempotency_key` rides along so an offline-queue replay (or a
// "committed but response lost" retry) is deduped server-side by the Phase 1
// backend idempotency. The backend's QuickOrderRequest ignores extra fields,
// so sending the key is safe even before that backend dedupe lands.
export async function openQuickOrder(body: {
  outlet_id: string;
  table_number?: string;
  items: { item_id: string; quantity: number }[];
  notes?: string;
  // Per-attempt key so a double-tap / warm-up / network replay of this exact
  // order returns the original instead of opening a duplicate (Task #373).
  idempotency_key?: string;
}): Promise<{
  order_id: string;
  total: number;
  items_count: number;
  idempotent_replay?: boolean;
}> {
  return api.post('/api/pos/mobile/quick-order', body);
}

// PUT /api/pos/mobile/order/{order_id}/status — advance/close the order
// lifecycle (pending → preparing → ready → served / cancelled).
export async function updateOrderStatus(
  orderId: string,
  status: OrderStatus,
  notes?: string,
): Promise<{ order_id: string; new_status: string }> {
  return api.put(`/api/pos/mobile/order/${encodeURIComponent(orderId)}/status`, {
    status,
    notes: notes || null,
  });
}

// POST /api/pos/transfer-table — scalar query params, no body. Moves an OPEN
// table transaction to another table (backend requires source status='open').
export async function transferTable(params: {
  from_table: string;
  to_table: string;
  outlet_id: string;
}): Promise<{ success: boolean; message: string; transaction_id?: string }> {
  return apiRequest('/api/pos/transfer-table', {
    method: 'POST',
    query: {
      from_table: params.from_table,
      to_table: params.to_table,
      outlet_id: params.outlet_id,
      transfer_all: true,
    },
  });
}

// The backend stores the close-order `payment_method` as a free string
// (pos_transactions.payment_method) — it neither validates against an enum nor
// changes the amount, so widening the mobile union to add bank transfer is
// purely additive and never weakens the close contract.
export type PaymentMethod = 'cash' | 'card' | 'transfer';

export type SplitType = 'equal' | 'custom';

export type SplitLine = {
  split_number: number;
  amount: number;
  items?: unknown;
};

export type SplitResult = {
  success: boolean;
  original_transaction_id: string;
  original_amount: number;
  split_type: string;
  split_count: number;
  splits: SplitLine[];
  // The backend re-sums the parts and reports whether they reconcile to the
  // collected total (delta within 1 kuruş). We surface `match` so the UI can
  // refuse to record a custom split that does not add up.
  total_validation: { expected: number; actual: number; delta: number; match: boolean };
};

// POST /api/pos/v2/orders/close — close an active order and take payment,
// writing a pos_transactions/completed row (the canonical close-order
// contract). The backend resolves the amount from the order's grand_total,
// enforces require_module("pos"), and is idempotent on idempotency_key +
// terminal-state (voided→409, already-closed/paid→idempotent success). We do
// not weaken any of that here — the mobile client only supplies the order id,
// payment method and a per-attempt idempotency key so a network/warm-up retry
// can never double-charge the same order.
export async function closeOrder(body: {
  order_id: string;
  payment_method: PaymentMethod;
  tip_amount?: number;
  idempotency_key?: string;
}): Promise<{
  order_id: string;
  transaction_id?: string;
  amount_paid?: number;
  payment_method?: string;
  idempotent?: boolean;
}> {
  return api.post('/api/pos/v2/orders/close', body);
}

// POST /api/pos/check-split — record how a CLOSED order's payment was divided
// (backend pos_fnb_router/pos_core.split_check). The order is already paid in
// full by closeOrder, which writes the canonical pos_transactions row; this
// only annotates that transaction with the agreed breakdown and re-validates
// that the parts reconcile to the collected total. It collects no money and
// never changes the close / idempotency contract — it is pure post-close
// bookkeeping for the receipt / who-paid split. `transaction_id`, `split_type`
// and `split_count` are scalar query params; the custom per-payer amounts ride
// in the embedded `{ split_details }` body the backend expects.
export async function checkSplit(params: {
  transaction_id: string;
  split_type: SplitType;
  split_count?: number;
  // custom split only — { "1": amount, "2": amount, ... } keyed by payer number.
  split_details?: Record<string, number>;
}): Promise<SplitResult> {
  return apiRequest('/api/pos/check-split', {
    method: 'POST',
    query: {
      transaction_id: params.transaction_id,
      split_type: params.split_type,
      ...(params.split_count ? { split_count: params.split_count } : {}),
    },
    body: params.split_details ? { split_details: params.split_details } : undefined,
  });
}

// POST /api/pos/create-order — posts the items as folio charges when a
// folio_id (or booking_id) is supplied (payment / room-folio transfer path).
export async function postOrderToFolio(body: {
  folio_id?: string;
  booking_id?: string;
  order_items: { item_id: string; quantity: number }[];
  // Per-attempt key so a double-tap / warm-up / network replay never posts the
  // same items as a second folio charge set (Task #373).
  idempotency_key?: string;
}): Promise<{ success: boolean; order_id: string; idempotent_replay?: boolean }> {
  return api.post('/api/pos/create-order', body);
}

// ── BEO (Banquet Event Order) — read-only ──────────────────────────────────
// The F&B / banquet team needs a readable hand sheet for catered events. These
// mirror backend/routers/mice.py: GET /api/mice/events (list, auth only) and
// GET /api/mice/events/{id}/beo (the BEO summary, auth only). Both are reads —
// no event write surface is exposed here; banquet writes stay gated by
// require_mice_ops / require_catalog on the backend.

export type BeoEventSummary = {
  id: string;
  name?: string;
  client_name?: string;
  event_type?: string;
  status?: string;
  expected_pax?: number;
  start_date?: string;
  end_date?: string;
};

export type BeoSpaceLine = {
  space_name?: string;
  starts_at?: string;
  ends_at?: string;
  setup_style?: string | null;
  expected_pax?: number | null;
};

export type BeoResourceLine = {
  name?: string;
  type?: string;
  quantity?: number;
  unit_price?: number;
};

export type BeoAgendaItem = {
  starts_at?: string;
  ends_at?: string;
  title?: string;
  kind?: string;
  owner?: string | null;
};

export type BeoPaymentMilestone = {
  due_date?: string;
  label?: string;
  amount?: number;
  paid?: boolean;
  reference?: string | null;
};

export type BeoStaffAssignment = {
  role?: string;
  name?: string;
  user?: string;
  notes?: string;
};

export type BeoTechnicalRequirements = {
  projector?: boolean;
  screen?: boolean;
  microphone_wired?: number;
  microphone_wireless?: number;
  sound_system?: boolean;
  stage?: boolean;
  lighting?: boolean;
  livestream?: boolean;
  internet_mbps?: number;
  translation_booths?: number;
  notes?: string | null;
};

export type BeoTotals = {
  space_total?: number;
  resources_total?: number;
  subtotal?: number;
  tax?: number;
  grand_total?: number;
  currency?: string;
};

export type BeoSummary = {
  event: {
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
    totals?: BeoTotals;
  };
  spaces: BeoSpaceLine[];
  resources: BeoResourceLine[];
  agenda: BeoAgendaItem[];
  payment_schedule: BeoPaymentMilestone[];
  technical_requirements?: BeoTechnicalRequirements | null;
  staff_assignments?: BeoStaffAssignment[];
  entertainment?: Record<string, unknown> | null;
};

// GET /api/mice/events?status= → { events, count }. Read-only event list that
// feeds the BEO picker (most-recent catered events).
export async function listBeoEvents(params?: { status?: string }): Promise<BeoEventSummary[]> {
  const res = await api.get<{ events?: BeoEventSummary[] }>('/api/mice/events', params);
  return res?.events ?? [];
}

// GET /api/mice/events/{id}/beo → the full Banquet Event Order summary.
export async function getBeo(eventId: string): Promise<BeoSummary> {
  return api.get<BeoSummary>(`/api/mice/events/${encodeURIComponent(eventId)}/beo`);
}

// Display helpers — the backend stores outlet/menu names under inconsistent
// keys across legacy and newer writers, so prefer the canonical field and
// fall back gracefully rather than showing a blank label.
export function outletLabel(o: Outlet): string {
  return o.outlet_name || o.name || '—';
}

export function menuItemLabel(m: MenuItem): string {
  return m.item_name || m.name || '—';
}

export type Reservation = {
  id: string;
  outlet_id: string;
  table_id: string;
  guest_name: string;
  pax: number;
  res_date: string;
  res_time: string;
  notes?: string;
  status: string;
};

export async function listReservations(params?: {
  outlet_id?: string;
  res_date?: string;
}): Promise<Reservation[]> {
  const res = await api.get<Reservation[]>('/api/pos/reservations', params);
  return res ?? [];
}

export async function createReservation(body: {
  outlet_id: string;
  table_id: string;
  guest_name: string;
  pax: number;
  res_date: string;
  res_time: string;
  notes?: string;
}): Promise<Reservation> {
  return api.post('/api/pos/reservations', body);
}

export async function updateReservationStatus(
  reservation_id: string,
  status: string,
): Promise<Reservation> {
  return api.put(`/api/pos/reservations/${encodeURIComponent(reservation_id)}/status`, {
    status,
  });
}

// --- SPA & Gym ---

export type SpaResource = {
  id: string;
  name: string;
  type: string;
  status: string;
};

export type SpaMembership = {
  id: string;
  guest_name: string;
  membership_type: string;
  start_date: string;
  end_date: string;
  price: number;
  status: string;
};

export type SpaReservation = {
  id: string;
  guest_name: string;
  service_item_id: string;
  therapist_id?: string;
  cabin_id?: string;
  res_date: string;
  res_time: string;
  duration_minutes: number;
  notes?: string;
  status: string;
  charged?: boolean;
};

export async function listSpaResources(params?: { resource_type?: string }): Promise<SpaResource[]> {
  const res = await api.get<SpaResource[]>('/api/pos/spa/resources', params);
  return res ?? [];
}

export async function listSpaMemberships(params?: { status?: string }): Promise<SpaMembership[]> {
  const res = await api.get<SpaMembership[]>('/api/pos/spa/memberships', params);
  return res ?? [];
}

export async function listSpaReservations(params?: { res_date?: string }): Promise<SpaReservation[]> {
  const res = await api.get<SpaReservation[]>('/api/pos/spa/reservations', params);
  return res ?? [];
}

export async function updateSpaReservationStatus(
  reservation_id: string,
  status: string,
): Promise<SpaReservation> {
  return api.put(`/api/pos/spa/reservations/${encodeURIComponent(reservation_id)}/status`, {
    status,
  });
}

export async function chargeSpaReservation(
  reservation_id: string,
  folio_id?: string,
): Promise<{ success: boolean; message: string; folio_id?: string }> {
  return api.post(`/api/pos/spa/reservations/${encodeURIComponent(reservation_id)}/charge`, {
    folio_id,
  });
}
