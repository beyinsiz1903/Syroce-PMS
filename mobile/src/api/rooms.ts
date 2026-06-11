import { api, apiRequest } from './client';

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

// PUT /api/housekeeping/room/{room_id}/status — used by housekeeping role to
// flip status. The backend takes `new_status` as a QUERY param (not a body),
// so we pass it via the query string. Valid statuses: available, occupied,
// dirty, cleaning, inspected, maintenance, out_of_order.
export async function updateRoomStatus(roomId: string, status: string): Promise<unknown> {
  try {
    return await apiRequest(`/api/housekeeping/room/${roomId}/status`, {
      method: 'PUT',
      query: { new_status: status },
    });
  } catch {
    // Fallback: pms-core hardening endpoint (RoomStatusUpdateRequest body).
    return api.post('/api/pms-core/housekeeping/room-status', {
      room_id: roomId,
      new_status: status,
    });
  }
}

// ── Housekeeping task assignment ──────────────────────────────────────────
export type HkStaff = {
  id?: string;
  name: string;
  role?: string;
};

// GET /api/housekeeping/mobile/staff — roster eligible for task assignment.
export async function listHousekeepingStaff(): Promise<HkStaff[]> {
  try {
    const res = await api.get<{ staff?: HkStaff[] }>('/api/housekeeping/mobile/staff');
    return Array.isArray(res?.staff) ? res.staff : [];
  } catch {
    return [];
  }
}

export type QuickTaskInput = {
  room_id: string;
  task_type: string;
  priority?: string;
  assigned_to?: string;
  notes?: string;
};

// POST /api/housekeeping/mobile/quick-task — assignment fires a push to the
// assignee and surfaces in their "Görevlerim" hub feed (matched by name).
export async function createQuickTask(input: QuickTaskInput): Promise<unknown> {
  return api.post('/api/housekeeping/mobile/quick-task', {
    priority: 'normal',
    ...input,
  });
}
