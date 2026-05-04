import { api } from './client';

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
