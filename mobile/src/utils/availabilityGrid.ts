// Pure helpers for the mobile availability grid (room x day). Kept free of
// React / network imports so they run under the plain `node:test` unit harness
// (see `yarn test:unit` / tsconfig.unit.json). These guard the occupancy logic
// that drives the operator's availability calendar: a regression here could
// show a busy room as free (double-booking risk) or a free room as blocked.

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

// Minimal structural shapes consumed by the grid builder. Real API types
// (AvailabilityRoom / RoomBlock) are structurally compatible with these.
export type GridRoomInput = {
  id: string;
  room_number?: string;
  room_type?: string;
  floor?: number | string;
  status?: string;
  available?: boolean;
  reason?: string;
  // Explicit, machine-readable occupancy discriminator from the availability
  // endpoint. Preferred over parsing the free-text `reason`.
  occupancy_status?: string;
};

// Normalizes the backend's explicit occupancy discriminator to a CellStatus,
// or null when the field is absent/unrecognized (so callers fall back to the
// legacy text heuristic). Tolerant of casing/whitespace.
export function normalizeOccupancyStatus(value?: string): CellStatus | null {
  switch ((value || '').trim().toLowerCase()) {
    case 'free':
      return 'free';
    case 'occupied':
      return 'occupied';
    case 'blocked':
      return 'blocked';
    default:
      return null;
  }
}

export type GridBlockInput = {
  room_id?: string;
  allow_sell?: boolean;
  start_date?: string;
  end_date?: string | null;
};

// YYYY-MM-DD + N days -> YYYY-MM-DD. Anchored at local midnight then sliced on
// the ISO prefix so it is stable regardless of the runner timezone.
export function addDaysISO(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

// The ordered list of day strings the grid spans, starting at startDate.
export function buildDayList(startDate: string, days: number): string[] {
  const dayList: string[] = [];
  for (let i = 0; i < days; i += 1) dayList.push(addDaysISO(startDate, i));
  return dayList;
}

// Room statuses that mark the room itself as unsellable (out of order / out of
// service / maintenance) regardless of the booking calendar.
export const BLOCKED_ROOM_STATUSES = new Set([
  'out_of_order',
  'out_of_service',
  'maintenance',
  'ooo',
  'oos',
]);

export function isBlockedRoomStatus(status?: string): boolean {
  return BLOCKED_ROOM_STATUSES.has((status || '').toLowerCase());
}

// Baseline cell status for a room on a single day, from that day's
// availability payload. OOO/OOS room status wins over the booking calendar.
// Otherwise we trust the backend's explicit `occupancy_status` discriminator
// (occupied > blocked > free) when present; only when it is missing do we fall
// back to the legacy free-text `reason` heuristic ("booked" -> occupied, else
// blocked) for backwards compatibility with older API responses.
export function cellStatusFromRoom(room: GridRoomInput): CellStatus {
  if (isBlockedRoomStatus(room.status)) return 'blocked';
  const explicit = normalizeOccupancyStatus(room.occupancy_status);
  if (explicit) return explicit;
  if (room.available === false) {
    const reason = (room.reason || '').toLowerCase();
    return reason.includes('booked') ? 'occupied' : 'blocked';
  }
  return 'free';
}

// Whether an active room block covers the given day. Range is start-inclusive,
// end-exclusive (day >= start && day < end) to match a checkout-day release.
// A missing start/end is treated as open-ended on that side. allow_sell blocks
// never cover a day — they are bookable despite the block.
export function blockCoversDay(block: GridBlockInput, day: string): boolean {
  if (block.allow_sell) return false;
  const start = block.start_date || '';
  const end = block.end_date || '';
  return (!start || day >= start) && (!end || day < end);
}

// Assembles the room x day grid from each day's availability payload plus the
// active room blocks. Precedence: occupied > blocked > free. Rooms are unioned
// across all days (a room present on only some days still gets a row) and
// sorted by room_number (Turkish, numeric-aware).
export function buildAvailabilityGrid(
  dayList: string[],
  perDay: GridRoomInput[][],
  blocks: GridBlockInput[],
): AvailabilityGrid {
  const roomMeta = new Map<string, AvailabilityGridRoom>();

  // Room roster: union across all days.
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
      meta.cells[day] = cellStatusFromRoom(r);
    });
  });

  // Overlay explicit room blocks (blocked beats free, occupied still wins).
  blocks.forEach((b) => {
    if (b.allow_sell || !b.room_id) return;
    const meta = roomMeta.get(b.room_id);
    if (!meta) return;
    dayList.forEach((day) => {
      if (!blockCoversDay(b, day)) return;
      if (meta.cells[day] !== 'occupied') meta.cells[day] = 'blocked';
    });
  });

  const rooms = Array.from(roomMeta.values()).sort((a, b) =>
    a.room_number.localeCompare(b.room_number, 'tr', { numeric: true }),
  );

  return { days: dayList, rooms };
}
