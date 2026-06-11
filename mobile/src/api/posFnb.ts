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
export async function openQuickOrder(body: {
  outlet_id: string;
  table_number?: string;
  items: { item_id: string; quantity: number }[];
  notes?: string;
}): Promise<{ order_id: string; total: number; items_count: number }> {
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

// POST /api/pos/create-order — posts the items as folio charges when a
// folio_id (or booking_id) is supplied (payment / room-folio transfer path).
export async function postOrderToFolio(body: {
  folio_id?: string;
  booking_id?: string;
  order_items: { item_id: string; quantity: number }[];
}): Promise<{ success: boolean; order_id: string }> {
  return api.post('/api/pos/create-order', body);
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
