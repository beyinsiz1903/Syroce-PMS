import { api } from './client';
import { type KbsIdentity } from '../utils/kbs';

export type KbsGuestReadiness = { guest_id: string; guest_name: string; ready: boolean; missing_fields: string[] };
export type KbsReadiness = { booking_id: string; ready: boolean; operational_visible?: boolean; enforced_at_checkin: boolean; expected_occupants: number; unregistered_occupants: number; guests: KbsGuestReadiness[] };
export type KbsJob = { id: string; booking_id: string; guest_id?: string; guest_name: string; room_number?: string; action: string; status: string; status_reason: string; delivery_uncertain: boolean; can_retry: boolean; kbs_test?: boolean; created_at?: string; completed_at?: string };
export type KbsNotifications = { items: KbsJob[]; total: number; skip: number; limit: number; has_more: boolean; counts: { sent: number; not_sent: number }; hidden_unresolved_count: number };
export type KbsCloudStatus = { configured: boolean; managed: boolean; enabled: boolean; verified: boolean; last_worker_at?: string | null; can_manage: boolean };

export const getKbsStatus = () => api.get<KbsCloudStatus>('/api/kbs/cloud/status');
export const getKbsNotifications = (skip = 0, bookingId?: string, group: 'sent' | 'not_sent' = 'not_sent') => api.get<KbsNotifications>('/api/kbs/mobile/notifications', { skip, limit: 50, booking_id: bookingId, group });
export const getKbsReadiness = (id: string) => api.get<KbsReadiness>(`/api/kbs/booking/${encodeURIComponent(id)}/readiness`);
export const updateKbsIdentity = (bookingId: string, guestId: string, body: Partial<KbsIdentity>) => api.put<KbsReadiness>(`/api/kbs/booking/${encodeURIComponent(bookingId)}/guests/${encodeURIComponent(guestId)}/identity`, body);
export const retryKbsNotification = (id: string) => api.post(`/api/kbs/queue/${encodeURIComponent(id)}/requeue?reason=mobile_identity_review`);
export const enqueueKbsGuest = (bookingId: string, guestId: string, action: 'checkin' | 'checkout') => api.post('/api/kbs/queue', { booking_id: bookingId, guest_id: guestId, action });
