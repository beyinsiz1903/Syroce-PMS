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
// Errors propagate so react-query's isError fires and the screen shows a
// visible error + retry instead of a misleading empty room list.
export async function listRooms(): Promise<Room[]> {
  const res = await api.get<RoomListResponse>('/api/pms/rooms');
  return unwrapRooms(res);
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
// Errors propagate so a failed roster load surfaces as a visible error rather
// than an empty (and misleading) assignee list.
export async function listHousekeepingStaff(): Promise<HkStaff[]> {
  const res = await api.get<{ staff?: HkStaff[] }>('/api/housekeeping/mobile/staff');
  return Array.isArray(res?.staff) ? res.staff : [];
}

// ── Open tasks per room (room card badge + detail sheet) ──────────────────
export type RoomTask = {
  id: string;
  room_id: string;
  room_number?: string;
  task_type?: string;
  assigned_to?: string | null;
  priority?: string;
  status?: string;
  notes?: string | null;
  created_at?: string | null;
};

// GET /api/housekeeping/mobile/room-tasks — flat list of open (non-done)
// housekeeping tasks across all rooms; the screen groups them by room_id to
// build the per-card open-task badge and the on-tap task list.
export async function listRoomTasks(): Promise<RoomTask[]> {
  const res = await api.get<{ tasks?: RoomTask[] }>('/api/housekeeping/mobile/room-tasks');
  return Array.isArray(res?.tasks) ? res.tasks : [];
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
