import { apiRequest, api } from './client';

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
  // Preferred path: opaque reference returned by uploadOnlineCheckinIdPhoto.
  // The legacy id_photo_base64 path still works server-side for backward
  // compatibility but is more bandwidth-heavy and risks JSON 4MB caps.
  id_photo_id?: string;
  id_photo_base64?: string;
  signature_text?: string;
  signature_svg?: string;
  signature_consent?: boolean;
};

export type IdPhotoUploadResult = {
  photo_id: string;
  sha256: string;
  content_type: string;
  size_bytes: number;
};

/**
 * Upload the guest's ID photo via multipart/form-data to the secure storage
 * endpoint. The server validates magic-bytes, encrypts the bytes at rest, and
 * returns an opaque `photo_id` to attach to the subsequent check-in submit.
 */
export async function uploadOnlineCheckinIdPhoto(
  bookingId: string,
  fileUri: string,
  mimeType = 'image/jpeg',
): Promise<IdPhotoUploadResult> {
  const form = new FormData();
  // React Native FormData accepts {uri, name, type} — TS type from RN is loose,
  // so we cast through unknown to satisfy the DOM lib's File contract.
  form.append('photo', {
    uri: fileUri,
    name: `id_photo_${Date.now()}.jpg`,
    type: mimeType,
  } as unknown as Blob);
  return apiRequest<IdPhotoUploadResult>(
    `/api/checkin/online/${encodeURIComponent(bookingId)}/id-photo`,
    { method: 'POST', body: form },
  );
}

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
