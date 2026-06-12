import { api } from './client';

export type QrTokenResponse = {
  token: string;
  expires_at: string;
  ttl_seconds: number;
  booking_id: string;
};

export type QrPendingChargeStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'expired'
  | 'failed';

export type QrPendingCharge = {
  id: string;
  outlet: string;
  outlet_name: string;
  amount: number;
  currency: string;
  description: string;
  status: QrPendingChargeStatus;
  created_at: string;
  expires_at: string;
  approved_at?: string | null;
  rejected_at?: string | null;
  failed_at?: string | null;
  folio_charge_id?: string | null;
  failure_reason?: string | null;
  rejection_reason?: string | null;
  items?: Array<{ name: string; qty: number; price: number }>;
};

export type QrPendingChargesResponse = {
  charges: QrPendingCharge[];
  pending_count: number;
};

// Errors propagate so react-query's isError fires and the QR screen shows the
// "no active booking / retry" path instead of a silently blank badge.
export async function fetchMyQrToken(): Promise<QrTokenResponse | null> {
  return api.get<QrTokenResponse>('/api/guest/qr/me');
}

export async function fetchMyPendingCharges(): Promise<QrPendingChargesResponse> {
  return api.get<QrPendingChargesResponse>('/api/guest/qr/charges/pending');
}

export async function approveQrCharge(chargeId: string): Promise<void> {
  await api.post(`/api/guest/qr/charges/${encodeURIComponent(chargeId)}/approve`);
}

export async function rejectQrCharge(chargeId: string, reason?: string): Promise<void> {
  await api.post(`/api/guest/qr/charges/${encodeURIComponent(chargeId)}/reject`, {
    reason: reason || null,
  });
}
