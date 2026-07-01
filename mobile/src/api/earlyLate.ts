import { api } from './client';

export type EarlyLateDirection = 'early_checkin' | 'late_checkout';

export type EarlyLateRule = {
  id?: string;
  label?: string;
  from_hour?: number;
  to_hour?: number;
  charge_type?: string;
  charge_value?: number;
};

export type EarlyLateCalcResponse = {
  applicable: boolean;
  amount: number;
  currency?: string;
  reason?: string;
  rule?: EarlyLateRule | null;
  actual_hour?: number;
  nightly_rate?: number;
  total?: number;
  nights?: number;
  label?: string;
};

export async function calculateEarlyLate(
  bookingId: string,
  direction: EarlyLateDirection,
  actualHour: number,
): Promise<EarlyLateCalcResponse> {
  return api.post<EarlyLateCalcResponse>('/api/pms/early-late/calculate', {
    booking_id: bookingId,
    direction,
    actual_hour: actualHour,
  });
}

/**
 * Submits the early-checkin / late-checkout request as a concierge ticket.
 * Uses /api/guest-journey/guest-request which does NOT require the booking
 * to be `checked_in` — so guests can request early check-in pre-arrival.
 */
export async function submitEarlyLateRequest(
  bookingId: string,
  direction: EarlyLateDirection,
  actualHour: number,
  amount: number,
  currency = 'TRY',
): Promise<{ success: boolean; request_id?: string; status?: string }> {
  const dirLabel = direction === 'early_checkin' ? 'Erken giriş' : 'Geç çıkış';
  const description = `${dirLabel} talebi — saat ${String(actualHour).padStart(2, '0')}:00 — tahmini ücret: ${amount.toFixed(2)} ${currency}`;
  return api.post('/api/guest-journey/guest-request', {
    booking_id: bookingId,
    request_type: 'concierge',
    description,
    priority: 'normal',
  });
}
