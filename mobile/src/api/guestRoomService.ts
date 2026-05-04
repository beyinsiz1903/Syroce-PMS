import { api } from './client';

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
