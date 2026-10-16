export const ROOM_PAGE_SIZE = 200;
export const ROOM_MAX_PAGES = 100;

export type RoomPageParams = { limit: number; offset: number };
type RoomRow = { id: string; room_number: string };
export type RoomDataFailure = 'invalid_page' | 'duplicate_room' | 'page_limit';

export class RoomDataError extends Error {
  readonly reason: RoomDataFailure;

  constructor(reason: RoomDataFailure) {
    super('Odalar yüklenemedi. Yeniden deneyin.');
    this.name = 'RoomDataError';
    this.reason = reason;
  }
}

const STRING_FIELDS = ['room_type', 'status', 'room_status', 'housekeeping_status', 'hk_status', 'current_booking_id', 'guest_name'] as const;
const HK_STRING_FIELDS = ['state', 'task_type', 'assigned_to_name', 'started_at'] as const;

function validRoom(value: unknown): value is RoomRow {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const room = value as Record<string, unknown>;
  if (typeof room.id !== 'string' || !room.id.trim()
    || typeof room.room_number !== 'string' || !room.room_number.trim()
    || !STRING_FIELDS.every((field) => room[field] == null || typeof room[field] === 'string')) return false;
  if (room.floor != null && typeof room.floor !== 'string'
    && !(typeof room.floor === 'number' && Number.isFinite(room.floor))) return false;
  if (room.housekeeping != null) {
    if (typeof room.housekeeping !== 'object' || Array.isArray(room.housekeeping)) return false;
    const hk = room.housekeeping as Record<string, unknown>;
    if (!HK_STRING_FIELDS.every((field) => hk[field] == null || typeof hk[field] === 'string')) return false;
    if (hk.elapsed_minutes != null && !(typeof hk.elapsed_minutes === 'number' && Number.isFinite(hk.elapsed_minutes) && hk.elapsed_minutes >= 0)) return false;
  }
  return true;
}

function unwrapRoomPage(value: unknown): unknown[] | undefined {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== 'object') return undefined;
  const page = value as { rooms?: unknown; items?: unknown };
  if (Array.isArray(page.rooms)) return page.rooms;
  if (Array.isArray(page.items)) return page.items;
  return undefined;
}

/** A short page proves completion. Never return earlier pages after a failed,
 * repeated or malformed page: incomplete inventory cannot establish vacancy. */
export async function loadRoomPages<T extends RoomRow>(
  requestPage: (params: RoomPageParams) => Promise<unknown>,
  options: { pageSize?: number; maxPages?: number } = {},
): Promise<T[]> {
  const pageSize = options.pageSize ?? ROOM_PAGE_SIZE;
  const maxPages = options.maxPages ?? ROOM_MAX_PAGES;
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 2000
    || !Number.isInteger(maxPages) || maxPages < 1 || maxPages > ROOM_MAX_PAGES) throw new RoomDataError('invalid_page');
  const rooms: T[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < maxPages; page += 1) {
    const rows = unwrapRoomPage(await requestPage({ limit: pageSize, offset: page * pageSize }));
    if (!rows || rows.length > pageSize || !rows.every(validRoom)) throw new RoomDataError('invalid_page');
    for (const room of rows) {
      if (seen.has(room.id)) throw new RoomDataError('duplicate_room');
      seen.add(room.id);
      rooms.push(room as T);
    }
    if (rows.length < pageSize) return rooms;
  }
  throw new RoomDataError('page_limit');
}
