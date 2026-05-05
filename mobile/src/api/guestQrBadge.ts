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

export async function fetchMyQrToken(): Promise<QrTokenResponse | null> {
  try {
    return await api.get<QrTokenResponse>('/api/guest/qr/me');
  } catch {
    return null;
  }
}

export async function fetchMyPendingCharges(): Promise<QrPendingChargesResponse> {
  try {
    return await api.get<QrPendingChargesResponse>('/api/guest/qr/charges/pending');
  } catch {
    return { charges: [], pending_count: 0 };
  }
}

export async function approveQrCharge(chargeId: string): Promise<void> {
  await api.post(`/api/guest/qr/charges/${encodeURIComponent(chargeId)}/approve`);
}

export async function rejectQrCharge(chargeId: string, reason?: string): Promise<void> {
  await api.post(`/api/guest/qr/charges/${encodeURIComponent(chargeId)}/reject`, {
    reason: reason || null,
  });
}
