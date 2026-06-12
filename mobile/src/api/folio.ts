import { api, apiRequest } from './client';

export type FolioCharge = {
  id: string;
  description?: string;
  amount?: number;
  total?: number;
  charge_category?: string;
  posted_at?: string;
};

export type FolioPayment = {
  id: string;
  amount?: number;
  method?: string;
  processed_at?: string;
};

export type Folio = {
  id: string;
  folio_number?: string;
  status?: string;
  balance?: number;
  charges?: FolioCharge[];
  payments?: FolioPayment[];
};

type FolioResponse =
  | Folio
  | {
      folio?: Folio;
      charges?: FolioCharge[];
      payments?: FolioPayment[];
      balance?: number;
      folio_number?: string;
      id?: string;
      status?: string;
    };

function normalizeFolio(res: FolioResponse | null): Folio | null {
  if (!res) return null;
  // Already a folio shape with id?
  if ('id' in res && typeof res.id === 'string' && !('folio' in res)) {
    return res as Folio;
  }
  const inner = (res as { folio?: Folio }).folio;
  if (inner && inner.id) {
    return {
      ...inner,
      charges: (res as { charges?: FolioCharge[] }).charges ?? inner.charges,
      payments: (res as { payments?: FolioPayment[] }).payments ?? inner.payments,
      balance: (res as { balance?: number }).balance ?? inner.balance,
    };
  }
  // Fallback: build a minimal folio from top-level fields
  const top = res as {
    id?: string;
    folio_number?: string;
    status?: string;
    balance?: number;
    charges?: FolioCharge[];
    payments?: FolioPayment[];
  };
  if (top.id || top.folio_number || top.charges) {
    return {
      id: top.id || top.folio_number || 'folio',
      folio_number: top.folio_number,
      status: top.status,
      balance: top.balance,
      charges: top.charges,
      payments: top.payments,
    };
  }
  return null;
}

// ── Finance folio listing (read-only) ──────────────────────────────────────
// Mirrors backend/routers/finance/folio.py. The list read only needs auth; the
// dashboard-stats read is gated by require_op("view_finance_reports") — the
// mobile (departments) finance entitlement decides whether we show the screen.

export type FolioListItem = {
  id: string;
  folio_number?: string;
  status?: string;
  balance?: number;
  guest_name?: string;
  room_number?: string;
  check_in?: string;
  check_out?: string;
  // Raw folio-doc timestamps passed through by /folio/list. `updated_at` (when
  // present) reflects the last folio mutation; we fall back to `created_at`.
  created_at?: string;
  updated_at?: string;
};

export type FolioListResponse = {
  folios: FolioListItem[];
  total: number;
};

export type FolioDashboardStats = {
  total_open_folios: number;
  total_outstanding_balance: number;
  recent_charges_24h?: number;
  recent_payments_24h?: number;
};

// GET /api/folio/list?status=&limit=&offset=
export async function listFolios(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<FolioListResponse> {
  const res = await api.get<Partial<FolioListResponse>>('/api/folio/list', params);
  return { folios: res?.folios ?? [], total: res?.total ?? 0 };
}

// GET /api/folio/dashboard-stats
export async function getFolioDashboardStats(): Promise<FolioDashboardStats> {
  const res = await api.get<Partial<FolioDashboardStats>>('/api/folio/dashboard-stats');
  return {
    total_open_folios: res?.total_open_folios ?? 0,
    total_outstanding_balance: res?.total_outstanding_balance ?? 0,
    recent_charges_24h: res?.recent_charges_24h ?? 0,
    recent_payments_24h: res?.recent_payments_24h ?? 0,
  };
}

// GET /api/frontdesk/folio/{booking_id} (frontdesk_router.py:514)
export async function getFolioForBooking(bookingId: string): Promise<Folio | null> {
  try {
    const res = await api.get<FolioResponse>(`/api/frontdesk/folio/${bookingId}`);
    return normalizeFolio(res);
  } catch {
    return null;
  }
}

// POST /api/frontdesk/folio/{booking_id}/payment (frontdesk_router.py:427)
export async function postPayment(
  bookingId: string,
  amount: number,
  method: 'cash' | 'card' | 'transfer' = 'cash',
): Promise<unknown> {
  return api.post(`/api/frontdesk/folio/${bookingId}/payment`, {
    amount,
    method,
    payment_type: 'final',
  });
}

// ── Folio-id detail + write actions (Task #457) ────────────────────────────
// These mirror backend/routers/finance/folio.py. Unlike the frontdesk reads
// above (keyed by booking_id), these are keyed by the FOLIO id surfaced by
// `listFolios` so the cashier folio-detail screen — and the front-desk / POS
// screens that link into it — share one source of truth. Writes pass an
// Idempotency-Key header so a double-tap / retry never posts twice (the
// backend replays the original response for the same key).

// Charge categories the backend's ChargeCategory enum accepts.
export type FolioChargeCategory =
  | 'food'
  | 'beverage'
  | 'minibar'
  | 'spa'
  | 'laundry'
  | 'phone'
  | 'parking'
  | 'service_charge'
  | 'other';

// Payment methods the backend's PaymentMethod enum accepts.
export type FolioPaymentMethod = 'cash' | 'card' | 'bank_transfer' | 'online';

// GET /api/folio/{folio_id} → { folio, charges, payments, balance }
export async function getFolioById(folioId: string): Promise<Folio | null> {
  const res = await api.get<FolioResponse>(`/api/folio/${folioId}`);
  return normalizeFolio(res);
}

// POST /api/folio/{folio_id}/charge — closed/unknown folios are rejected 404
// server-side ("Folio not found or closed"); the caller surfaces that message.
export async function postFolioCharge(
  folioId: string,
  body: {
    charge_category: FolioChargeCategory;
    description: string;
    amount: number;
    quantity?: number;
  },
  idempotencyKey: string,
): Promise<FolioCharge> {
  return apiRequest<FolioCharge>(`/api/folio/${folioId}/charge`, {
    method: 'POST',
    body: { quantity: 1, ...body },
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

// POST /api/folio/{folio_id}/payment
export async function postFolioPayment(
  folioId: string,
  body: {
    amount: number;
    method: FolioPaymentMethod;
    payment_type?: string;
  },
  idempotencyKey: string,
): Promise<FolioPayment> {
  return apiRequest<FolioPayment>(`/api/folio/${folioId}/payment`, {
    method: 'POST',
    body: { payment_type: 'interim', ...body },
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}
