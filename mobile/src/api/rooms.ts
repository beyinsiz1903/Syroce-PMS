import { api } from './client';

export type Room = {
  id: string;
  room_number: string;
  room_type?: string;
  floor?: number | string;
  status?: string;
  current_booking_id?: string;
  guest_name?: string;
};

type RoomListResponse = Room[] | { rooms?: Room[]; items?: Room[] };

function unwrapRooms(res: RoomListResponse): Room[] {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.rooms)) return res.rooms;
  if (Array.isArray(res?.items)) return res.items;
  return [];
}

// GET /api/pms/rooms (pms_rooms.py)
export async function listRooms(): Promise<Room[]> {
  try {
    const res = await api.get<RoomListResponse>('/api/pms/rooms');
    return unwrapRooms(res);
  } catch {
    return [];
  }
}

export async function findAvailableRoomByType(roomType: string): Promise<Room | null> {
  const rooms = await listRooms();
  return (
    rooms.find(
      (r) =>
        (r.room_type || '').toLowerCase() === roomType.toLowerCase() &&
        ['available', 'clean', 'inspected'].includes((r.status || '').toLowerCase()),
    ) || null
  );
}

// PUT /api/housekeeping/room/{room_id}/status — used by housekeeping role to flip status
export async function updateRoomStatus(roomId: string, status: string): Promise<unknown> {
  try {
    return await api.put(`/api/housekeeping/room/${roomId}/status`, { status });
  } catch {
    // Fallback: pms-core hardening endpoint
    return api.post('/api/pms-core/housekeeping/room-status', {
      room_id: roomId,
      status,
    });
  }
}
