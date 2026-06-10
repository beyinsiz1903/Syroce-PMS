import { api } from './client';

// Accounting API client — read-focused mirror of backend accounting endpoints
// (backend/domains/accounting/endpoints.py + backend/routers/finance/accounting.py).
// GET reads only require authentication server-side; the mobile (departments)
// entitlement (view_finance_reports roles) decides whether we show the screen.
// Writes stay gated by require_op("view_finance_reports") on the backend and are
// intentionally NOT exposed here — this surface is read-only.

export type Expense = {
  id: string;
  expense_number?: string;
  category?: string;
  description?: string;
  amount?: number;
  vat_rate?: number;
  vat_amount?: number;
  total_amount?: number;
  date?: string;
  payment_status?: string;
  payment_method?: string | null;
  notes?: string | null;
};

export type AccountingInvoice = {
  id: string;
  invoice_number?: string;
  invoice_type?: string;
  customer_name?: string;
  status?: string;
  subtotal?: number;
  total_vat?: number;
  total?: number;
  issue_date?: string;
  due_date?: string;
  payment_date?: string | null;
  notes?: string | null;
};

export type InventoryItem = {
  id: string;
  name?: string;
  sku?: string | null;
  category?: string;
  unit?: string;
  quantity?: number;
  unit_cost?: number;
  reorder_level?: number;
  location?: string | null;
};

export type InventorySummary = {
  items: InventoryItem[];
  low_stock_count: number;
  total_value: number;
};

// GET /api/accounting/expenses?start_date=&end_date=&category=
export async function listExpenses(params?: {
  start_date?: string;
  end_date?: string;
  category?: string;
}): Promise<Expense[]> {
  const res = await api.get<Expense[]>('/api/accounting/expenses', params);
  return res ?? [];
}

// GET /api/accounting/invoices?start_date=&end_date=&invoice_type=&status=
export async function listInvoices(params?: {
  start_date?: string;
  end_date?: string;
  invoice_type?: string;
  status?: string;
}): Promise<AccountingInvoice[]> {
  const res = await api.get<AccountingInvoice[]>('/api/accounting/invoices', params);
  return res ?? [];
}

// GET /api/accounting/inventory → { items, low_stock_count, total_value }
export async function getInventory(): Promise<InventorySummary> {
  const res = await api.get<Partial<InventorySummary>>('/api/accounting/inventory');
  return {
    items: res?.items ?? [],
    low_stock_count: res?.low_stock_count ?? 0,
    total_value: res?.total_value ?? 0,
  };
}
