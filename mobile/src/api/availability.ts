import { api } from './client';
import {
  addDaysISO,
  buildAvailabilityGrid,
  buildDayList,
} from '../utils/availabilityGrid';
import type {
  AvailabilityGrid,
  AvailabilityGridRoom,
  CellStatus,
} from '../utils/availabilityGrid';

export type { AvailabilityGrid, AvailabilityGridRoom, CellStatus };

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

// Builds a room-by-day grid by querying availability for each day in the
// range and overlaying active room blocks. The pure assembly + precedence
// rules live in utils/availabilityGrid (occupied > blocked > free); this
// wrapper only does the I/O.
export async function getAvailabilityGrid(
  startDate: string,
  days: number,
  roomType?: string,
): Promise<AvailabilityGrid> {
  const dayList = buildDayList(startDate, days);

  const endExclusive = addDaysISO(startDate, days);
  const [perDay, blocks] = await Promise.all([
    Promise.all(dayList.map((d) => getAvailability(d, addDaysISO(d, 1), roomType))),
    getRoomBlocks(startDate, endExclusive),
  ]);

  return buildAvailabilityGrid(dayList, perDay, blocks);
}
