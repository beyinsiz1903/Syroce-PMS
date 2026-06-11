import { api } from './client';

// Procurement API client — read-focused mirror of backend/routers/procurement.py
// (mounted under /api/procurement). The list endpoints (GET purchase-requests /
// purchase-orders) only require auth server-side; PR/PO state changes stay
// gated by require_procurement + require_op("manage_sales") on the backend and
// are NOT exposed here. The (departments) procurement entitlement decides
// whether we show the screen.

export type PurchaseRequestLine = {
  item_name?: string;
  quantity?: number;
  unit?: string;
  est_unit_cost?: number;
  notes?: string | null;
};

export type PurchaseRequest = {
  id: string;
  pr_no?: string;
  status?: string;
  requester?: string | null;
  department?: string;
  needed_by?: string | null;
  notes?: string | null;
  lines?: PurchaseRequestLine[];
  lines_total?: number;
  created_at?: string;
};

export type PurchaseOrderLine = {
  item_name?: string;
  quantity?: number;
  unit?: string;
  unit_cost?: number;
  line_total?: number;
  received_qty?: number;
};

export type PurchaseOrder = {
  id: string;
  po_no?: string;
  status?: string;
  supplier_id?: string;
  supplier_name?: string | null;
  currency?: string;
  tax_rate?: number;
  lines?: PurchaseOrderLine[];
  subtotal?: number;
  tax_total?: number;
  grand_total?: number;
  expected_delivery?: string | null;
  notes?: string | null;
  created_at?: string;
};

// GET /api/procurement/purchase-requests?status=&department= → { items, count }
export async function listPurchaseRequests(params?: {
  status?: string;
  department?: string;
}): Promise<PurchaseRequest[]> {
  const res = await api.get<{ items?: PurchaseRequest[] }>(
    '/api/procurement/purchase-requests',
    params,
  );
  return res?.items ?? [];
}

// GET /api/procurement/purchase-orders?status=&supplier_id= → { items, count }
export async function listPurchaseOrders(params?: {
  status?: string;
  supplier_id?: string;
}): Promise<PurchaseOrder[]> {
  const res = await api.get<{ items?: PurchaseOrder[] }>(
    '/api/procurement/purchase-orders',
    params,
  );
  return res?.items ?? [];
}
