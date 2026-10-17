import { api } from './client';
import { parseRoomRequestDetail, parseRoomRequests, roomRequestPath } from '../utils/guestRequests';

export async function getRoomRequestAccess(): Promise<{ can_view: boolean }> {
  const result = await api.get<{ can_view?: unknown }>('/api/messaging/guest-requests/access');
  if (typeof result?.can_view !== 'boolean') throw new Error('Misafir talepleri erişimi doğrulanamadı.');
  return { can_view: result.can_view };
}
export async function getRoomRequests() {
  return parseRoomRequests(await api.get('/api/messaging/guest-requests/threads'));
}
export async function getRoomRequestThread(roomId: string) {
  return parseRoomRequestDetail(await api.get(roomRequestPath(roomId)), roomId);
}
export async function replyToRoomRequest(roomId: string, message: string) {
  const text = message.trim();
  if (!text || text.length > 2000) throw new Error('Yanıt 1–2000 karakter olmalıdır.');
  return api.post(`${roomRequestPath(roomId)}/reply`, { message: text });
}
export async function markRoomRequestsRead(roomId: string) {
  return api.post(`${roomRequestPath(roomId)}/mark-read`, {});
}
