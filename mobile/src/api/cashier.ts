import { api } from './client';

// Cashier (Kasa) API client — read-focused mirror of
// backend/domains/pms/cashier_router.py. The current-shift read is gated by
// require_op("view_finance_reports") server-side; writes (open/close/handover/
// manual-transaction) stay gated by require_op("post_payment") on the backend
// and are intentionally NOT exposed here — this mobile surface is read-only.

export type CashierTransaction = {
  id?: string;
  amount?: number;
  direction?: 'in' | 'out' | string;
  method?: string;
  type?: string;
  description?: string;
  created_at?: string;
};

export type CashierShift = {
  id?: string;
  cashier_name?: string;
  opening_amount?: number;
  cash_in?: number;
  cash_out?: number;
  status?: string;
  opened_at?: string;
  currency?: string;
};

export type CurrentShiftResponse = {
  shift: CashierShift | null;
  transactions: CashierTransaction[];
};

// GET /api/cashier/current-shift → { shift, transactions }
export async function getCurrentShift(): Promise<CurrentShiftResponse> {
  const res = await api.get<Partial<CurrentShiftResponse>>('/api/cashier/current-shift');
  return {
    shift: res?.shift ?? null,
    transactions: res?.transactions ?? [],
  };
}

// Net expected cash in the drawer (opening + cash_in - cash_out). Mirrors the
// backend's `expected` computation in close/handover so the mobile summary
// matches what the cashier sees at close time.
export function expectedCash(shift: CashierShift | null): number {
  if (!shift) return 0;
  return (
    (shift.opening_amount ?? 0) + (shift.cash_in ?? 0) - (shift.cash_out ?? 0)
  );
}
