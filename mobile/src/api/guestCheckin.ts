import { api } from './client';

export type OnlineCheckinPayload = {
  booking_id: string;
  passport_number?: string;
  passport_expiry?: string;
  nationality?: string;
  estimated_arrival_time?: string;
  flight_number?: string;
  coming_from?: string;
  special_requests?: string;
  dietary_restrictions?: string;
  accessibility_needs?: string;
  mobile_number?: string;
  whatsapp_number?: string;
  // Identity + digital signature (V2 mobile guest app)
  id_photo_base64?: string;
  signature_text?: string;
  signature_consent?: boolean;
};

export type OnlineCheckinResult = {
  checkin_id: string;
  booking_id: string;
  status: string;
  room_number?: string | null;
  estimated_ready_time?: string | null;
  upsell_offers?: Array<Record<string, unknown>>;
  check_in_instructions?: string;
  message?: string;
};

export async function submitOnlineCheckin(
  payload: OnlineCheckinPayload,
): Promise<OnlineCheckinResult> {
  return api.post<OnlineCheckinResult>('/api/checkin/online', payload);
}

export type OnlineCheckinStatus = {
  completed: boolean;
  checkin: Record<string, unknown> | null;
};

export async function getOnlineCheckinStatus(bookingId: string): Promise<OnlineCheckinStatus> {
  try {
    return await api.get<OnlineCheckinStatus>(`/api/checkin/online/${bookingId}`);
  } catch {
    return { completed: false, checkin: null };
  }
}
