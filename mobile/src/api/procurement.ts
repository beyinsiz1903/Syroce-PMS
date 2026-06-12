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

export type GoodsReceipt = {
  id: string;
  grn_no?: string;
  received_at?: string | null;
  received_by?: string | null;
  notes?: string | null;
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
  status_reason?: string | null;
  source_pr_id?: string | null;
  grns?: GoodsReceipt[];
  created_at?: string;
};

// Mirrors GET /api/procurement/suppliers/{id}/credit-utilisation. View-only —
// the create-PO guard already enforces the hard 409 server-side; this is the
// same warning logic surfaced read-only so buyers can see exposure on the PO.
export type SupplierCreditUtilisation = {
  supplier_id: string;
  supplier_name?: string | null;
  limit: number | null;
  open_total: number;
  projected_amount: number;
  projected_total: number;
  headroom: number | null;
  used_pct: number | null;
  warning: boolean;
  exceeded: boolean;
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

// GET /api/procurement/purchase-requests/{id} → full PR doc
export async function getPurchaseRequest(id: string): Promise<PurchaseRequest> {
  return api.get<PurchaseRequest>(`/api/procurement/purchase-requests/${id}`);
}

// GET /api/procurement/purchase-orders/{id} → full PO doc (incl. grns[])
export async function getPurchaseOrder(id: string): Promise<PurchaseOrder> {
  return api.get<PurchaseOrder>(`/api/procurement/purchase-orders/${id}`);
}

// Permitted PR decisions the mobile detail surfaces. The backend enforces the
// submitted → approved/rejected transition + require_op("manage_sales") +
// require_procurement; a rejection reason must be >= 5 chars server-side.
export type PrStatusAction = 'approved' | 'rejected';

// POST /api/procurement/purchase-requests/{id}/status
export async function changePrStatus(
  id: string,
  status: PrStatusAction,
  reason?: string,
): Promise<PurchaseRequest> {
  return api.post<PurchaseRequest>(`/api/procurement/purchase-requests/${id}/status`, {
    status,
    ...(reason ? { reason } : {}),
  });
}

// Permitted PO decisions the mobile detail surfaces. Backend transition map:
// draft→sent|cancelled, sent→cancelled, partially_received→cancelled,
// received→closed. Cancel requires a reason >= 5 chars server-side.
export type PoStatusAction = 'sent' | 'cancelled' | 'closed';

// POST /api/procurement/purchase-orders/{id}/status
export async function changePoStatus(
  id: string,
  status: PoStatusAction,
  reason?: string,
): Promise<PurchaseOrder> {
  return api.post<PurchaseOrder>(`/api/procurement/purchase-orders/${id}/status`, {
    status,
    ...(reason ? { reason } : {}),
  });
}

// GET /api/procurement/suppliers/{id}/credit-utilisation — view-only credit
// exposure. Requires view_finance_reports server-side, so callers gate the
// request on the finance-reports entitlement.
export async function getSupplierCreditUtilisation(
  supplierId: string,
): Promise<SupplierCreditUtilisation> {
  return api.get<SupplierCreditUtilisation>(
    `/api/procurement/suppliers/${supplierId}/credit-utilisation`,
  );
}
