import { api } from './client';

export type AvailabilityBlock = {
  type?: string;
  allow_sell?: boolean;
  start_date?: string;
  end_date?: string | null;
};

// GET /api/pms/rooms/availability spreads the full room doc and adds
// available / reason / blocks for the requested window.
export type AvailabilityRoom = {
  id: string;
  room_number?: string;
  room_type?: string;
  floor?: number | string;
  status?: string;
  available?: boolean;
  reason?: string;
  blocks?: AvailabilityBlock[];
};

type AvailabilityResponse = AvailabilityRoom[] | { rooms?: AvailabilityRoom[]; items?: AvailabilityRoom[] };

function unwrap(res: AvailabilityResponse): AvailabilityRoom[] {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.rooms)) return res.rooms;
  if (Array.isArray(res?.items)) return res.items;
  return [];
}

// GET /api/pms/rooms/availability?check_in&check_out — per-room availability
// across a single window.
export async function getAvailability(
  checkIn: string,
  checkOut: string,
  roomType?: string,
): Promise<AvailabilityRoom[]> {
  const res = await api.get<AvailabilityResponse>('/api/pms/rooms/availability', {
    check_in: checkIn,
    check_out: checkOut,
    room_type: roomType || undefined,
  });
  return unwrap(res);
}

export type RoomBlock = {
  id: string;
  room_id?: string;
  type?: string;
  status?: string;
  reason?: string;
  start_date?: string;
  end_date?: string | null;
  allow_sell?: boolean;
};

type RoomBlockResponse = RoomBlock[] | { blocks?: RoomBlock[]; items?: RoomBlock[] };

// GET /api/pms/room-blocks — active blocks overlapping the requested window.
export async function getRoomBlocks(fromDate?: string, toDate?: string): Promise<RoomBlock[]> {
  try {
    const res = await api.get<RoomBlockResponse>('/api/pms/room-blocks', {
      status: 'active',
      from_date: fromDate || undefined,
      to_date: toDate || undefined,
    });
    if (Array.isArray(res)) return res;
    if (Array.isArray(res?.blocks)) return res.blocks;
    if (Array.isArray(res?.items)) return res.items;
    return [];
  } catch {
    return [];
  }
}

export type CellStatus = 'free' | 'occupied' | 'blocked';

export type AvailabilityGridRoom = {
  id: string;
  room_number: string;
  room_type?: string;
  floor?: number | string;
  cells: Record<string, CellStatus>;
};

export type AvailabilityGrid = {
  days: string[];
  rooms: AvailabilityGridRoom[];
};

function addDaysISO(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

const BLOCKED_ROOM_STATUSES = new Set([
  'out_of_order',
  'out_of_service',
  'maintenance',
  'ooo',
  'oos',
]);

// Builds a room-by-day grid by querying availability for each day in the
// range and overlaying active room blocks. Occupied takes precedence over
// blocked, which takes precedence over free.
export async function getAvailabilityGrid(
  startDate: string,
  days: number,
  roomType?: string,
): Promise<AvailabilityGrid> {
  const dayList: string[] = [];
  for (let i = 0; i < days; i += 1) dayList.push(addDaysISO(startDate, i));

  const endExclusive = addDaysISO(startDate, days);
  const [perDay, blocks] = await Promise.all([
    Promise.all(dayList.map((d) => getAvailability(d, addDaysISO(d, 1), roomType))),
    getRoomBlocks(startDate, endExclusive),
  ]);

  // Room roster: union across all days so a room only present on some days
  // still gets a row.
  const roomMeta = new Map<string, AvailabilityGridRoom>();
  perDay.forEach((rooms) => {
    rooms.forEach((r) => {
      if (!r.id) return;
      if (!roomMeta.has(r.id)) {
        roomMeta.set(r.id, {
          id: r.id,
          room_number: r.room_number || r.id,
          room_type: r.room_type,
          floor: r.floor,
          cells: {},
        });
      }
    });
  });

  // Baseline from each day's availability + the room's own OOO/OOS status.
  perDay.forEach((rooms, dayIdx) => {
    const day = dayList[dayIdx];
    rooms.forEach((r) => {
      const meta = roomMeta.get(r.id);
      if (!meta) return;
      let status: CellStatus;
      if (BLOCKED_ROOM_STATUSES.has((r.status || '').toLowerCase())) {
        status = 'blocked';
      } else if (r.available === false) {
        const reason = (r.reason || '').toLowerCase();
        status = reason.includes('booked') ? 'occupied' : 'blocked';
      } else {
        status = 'free';
      }
      meta.cells[day] = status;
    });
  });

  // Overlay explicit room blocks (blocked beats free, occupied still wins).
  blocks.forEach((b) => {
    if (b.allow_sell || !b.room_id) return;
    const meta = roomMeta.get(b.room_id);
    if (!meta) return;
    dayList.forEach((day) => {
      const start = b.start_date || '';
      const end = b.end_date || '';
      const inRange = (!start || day >= start) && (!end || day < end);
      if (!inRange) return;
      if (meta.cells[day] !== 'occupied') meta.cells[day] = 'blocked';
    });
  });

  const rooms = Array.from(roomMeta.values()).sort((a, b) =>
    a.room_number.localeCompare(b.room_number, 'tr', { numeric: true }),
  );

  return { days: dayList, rooms };
}
