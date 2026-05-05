import { api, getApiUrl, getToken } from './client';

export type MenuItem = {
  id: string;
  name: string;
  price: number;
  description?: string;
  category?: string;
  available?: boolean;
};

export type MenuCategory = {
  name: string;
  items: MenuItem[];
};

export type MenuResponse = {
  categories: MenuCategory[];
};

export async function getRoomServiceMenu(): Promise<MenuResponse> {
  try {
    return await api.get<MenuResponse>('/api/guest/room-service-menu');
  } catch {
    return { categories: [] };
  }
}

export type OrderItemPayload = {
  id?: string;
  name: string;
  price: number;
  quantity: number;
};

export type CreateOrderResponse = {
  success: boolean;
  order_id: string;
  estimated_delivery?: string;
  total_amount?: number;
};

export async function createRoomServiceOrder(
  bookingId: string,
  items: OrderItemPayload[],
  specialInstructions?: string,
): Promise<CreateOrderResponse> {
  return api.post<CreateOrderResponse>('/api/guest/room-service-order', {
    booking_id: bookingId,
    items,
    special_instructions: specialInstructions,
  });
}

export type RoomServiceOrder = {
  id: string;
  booking_id?: string;
  items?: OrderItemPayload[];
  total_amount?: number;
  status?: string;
  ordered_at?: string;
  estimated_delivery?: string;
  special_instructions?: string;
};

export async function listRoomServiceOrders(bookingId: string): Promise<RoomServiceOrder[]> {
  try {
    const res = await api.get<{ orders: RoomServiceOrder[] }>(
      `/api/guest/room-service-orders/${bookingId}`,
    );
    return res?.orders || [];
  } catch {
    return [];
  }
}

export type RoomServiceOrderEvent = {
  type: 'room_service_order';
  event: 'created' | 'status_changed' | string;
  order: RoomServiceOrder;
  timestamp?: string;
};

export type RoomServiceStreamHandlers = {
  onEvent: (ev: RoomServiceOrderEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: unknown) => void;
};

function httpToWs(url: string): string {
  if (url.startsWith('https://')) return 'wss://' + url.slice('https://'.length);
  if (url.startsWith('http://')) return 'ws://' + url.slice('http://'.length);
  return url;
}

// Open the per-booking order WS. Returns an unsubscribe that closes the
// socket and suppresses further callbacks. JWT goes in `?token=` since
// RN's WebSocket can't set headers; no token / no booking → no-op.
export async function subscribeRoomServiceOrders(
  bookingId: string,
  handlers: RoomServiceStreamHandlers,
): Promise<() => void> {
  const token = await getToken();
  if (!token || !bookingId) {
    return () => undefined;
  }
  const base = httpToWs(getApiUrl());
  const url = `${base}/api/guest/ws/room-service-orders/${encodeURIComponent(bookingId)}?token=${encodeURIComponent(
    token,
  )}`;

  let closedByCaller = false;
  let ws: WebSocket | null = null;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    handlers.onError?.(err);
    return () => undefined;
  }

  ws.onopen = () => {
    if (closedByCaller) return;
    handlers.onOpen?.();
  };
  ws.onmessage = (msg: { data?: unknown }) => {
    if (closedByCaller) return;
    if (typeof msg?.data !== 'string') return;
    try {
      const parsed = JSON.parse(msg.data);
      if (parsed && parsed.type === 'room_service_order' && parsed.order) {
        handlers.onEvent(parsed as RoomServiceOrderEvent);
      }
    } catch {
      /* non-JSON frame ignored */
    }
  };
  ws.onerror = (err: unknown) => {
    if (closedByCaller) return;
    handlers.onError?.(err);
  };
  ws.onclose = () => {
    if (closedByCaller) return;
    handlers.onClose?.();
  };

  return () => {
    closedByCaller = true;
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}

export async function updateRoomServiceOrderStatus(
  orderId: string,
  status: 'pending' | 'confirmed' | 'preparing' | 'delivered' | 'cancelled',
): Promise<{ success: boolean; order_id: string; status: string }> {
  return api.patch<{ success: boolean; order_id: string; status: string }>(
    `/api/guest/room-service-orders/${orderId}/status`,
    { status },
  );
}
