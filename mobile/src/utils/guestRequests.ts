// Staff use the room/QR request stream, not internal chat or guest accounts.
export type RoomRequestSummary = {
  room_id: string; room_number?: string | null; last_body?: string | null;
  last_sender_type?: string | null; last_category?: string | null;
  last_created_at?: string | null; total: number; unread: number;
};
export type RoomRequestMessage = {
  id: string; room_id: string; room_number?: string | null; booking_id?: string | null;
  sender_type: 'guest' | 'staff'; sender_name?: string | null; body: string;
  category?: string | null; department?: string | null; priority?: string | null;
  request_id?: string | null; created_at?: string | null; read?: boolean;
};
export type RoomRequests = { threads: RoomRequestSummary[]; total_unread: number };
export type RoomRequestDetail = { room_id: string; room_number?: string | null; messages: RoomRequestMessage[] };

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function optionalStrings(value: Record<string, unknown>, keys: string[]): boolean {
  return keys.every(key => value[key] == null || typeof value[key] === 'string');
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function invalid(): never {
  throw new Error('Misafir talepleri doğrulanamadı. Lütfen yeniden deneyin.');
}
export function roomRequestPath(roomId: string): string {
  // wa_* conversations are WhatsApp contacts, not rooms.
  if (!roomId.trim() || roomId.startsWith('wa_')) throw new Error('Geçerli bir oda seçin.');
  return `/api/messaging/guest-requests/threads/${encodeURIComponent(roomId)}`;
}
export function parseRoomRequests(payload: unknown): RoomRequests {
  if (!object(payload) || !Array.isArray(payload.threads)) return invalid();
  const threads = payload.threads.map((row): RoomRequestSummary => {
    if (!object(row) || typeof row.room_id !== 'string' || !row.room_id.trim()
      || !count(row.unread) || !count(row.total)
      || !optionalStrings(row, ['room_number', 'last_body', 'last_sender_type', 'last_category', 'last_created_at'])) return invalid();
    return row as RoomRequestSummary;
  }).filter(row => !row.room_id.startsWith('wa_'));
  if (new Set(threads.map(row => row.room_id)).size !== threads.length) return invalid();
  threads.sort((a, b) => (b.last_created_at || '').localeCompare(a.last_created_at || ''));
  return { threads, total_unread: threads.reduce((sum, row) => sum + row.unread, 0) };
}
export function parseRoomRequestDetail(payload: unknown, roomId: string): RoomRequestDetail {
  if (!object(payload) || payload.room_id !== roomId || !Array.isArray(payload.messages)
    || !optionalStrings(payload, ['room_number'])) return invalid();
  const messages = payload.messages.map((row): RoomRequestMessage => {
    if (!object(row) || typeof row.id !== 'string' || !row.id || row.room_id !== roomId
      || typeof row.body !== 'string' || !['guest', 'staff'].includes(String(row.sender_type))
      || (row.read != null && typeof row.read !== 'boolean')
      || !optionalStrings(row, ['room_number', 'booking_id', 'sender_name', 'category', 'department', 'priority', 'request_id', 'created_at'])) return invalid();
    return row as RoomRequestMessage;
  });
  if (new Set(messages.map(row => row.id)).size !== messages.length) return invalid();
  messages.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  return { room_id: roomId, room_number: payload.room_number as string | null | undefined, messages };
}
export function filterRoomRequests(threads: RoomRequestSummary[], search: string, unreadOnly: boolean): RoomRequestSummary[] {
  const needle = search.trim().toLocaleLowerCase('tr-TR');
  return threads.filter(row => (!unreadOnly || row.unread > 0) && (!needle
    || `${row.room_number || ''} ${row.last_body || ''}`.toLocaleLowerCase('tr-TR').includes(needle)));
}
export function roomRequestCategory(value?: string | null): string {
  const labels: Record<string, string> = {
    rooms: 'Oda / Temizlik', minibar: 'Minibar', laundry: 'Çamaşır', technical: 'Teknik Servis',
    fnb: 'Yiyecek & İçecek', spa: 'Spa', transportation: 'Ulaşım', other: 'Diğer',
  };
  return labels[value || ''] || 'Misafir talebi';
}
