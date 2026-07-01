import { api } from './client';

export type GuestMessage = {
  id: string;
  booking_id?: string | null;
  guest_user_id?: string | null;
  guest_name?: string;
  room_number?: string | null;
  sender: 'guest' | 'staff' | string;
  sender_name?: string;
  message: string;
  message_type?: string;
  read?: boolean;
  created_at?: string;
};

export type GuestConversation = {
  booking_id?: string | null;
  guest_name?: string;
  guest_user_id?: string | null;
  room_number?: string | null;
  messages: GuestMessage[];
  unread_count: number;
  last_message_at?: string;
};

export type GuestMessagesResponse = {
  conversations: GuestConversation[];
  total_messages: number;
  unread_total: number;
};

export async function getGuestMessages(): Promise<GuestMessagesResponse> {
  try {
    return await api.get<GuestMessagesResponse>('/api/guest/messages');
  } catch {
    return { conversations: [], total_messages: 0, unread_total: 0 };
  }
}

export async function sendGuestMessage(
  message: string,
  bookingId?: string,
  messageType: string = 'general',
): Promise<GuestMessage> {
  return api.post<GuestMessage>('/api/guest/messages', {
    booking_id: bookingId,
    message,
    message_type: messageType,
  });
}

export async function markAllRead(bookingId?: string): Promise<{ marked_read: number }> {
  try {
    return await api.put<{ marked_read: number }>(
      `/api/guest/messages/mark-all-read${bookingId ? `?booking_id=${encodeURIComponent(bookingId)}` : ''}`,
      {},
    );
  } catch {
    return { marked_read: 0 };
  }
}

export async function getUnreadCount(): Promise<number> {
  try {
    const res = await api.get<{ unread_count: number }>('/api/guest/messages/unread-count');
    return res?.unread_count || 0;
  } catch {
    return 0;
  }
}
