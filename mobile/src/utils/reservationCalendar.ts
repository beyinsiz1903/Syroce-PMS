// Pure helpers for the reservation calendar showcase (room x day timeline).
// React / network free so they run under the plain `node:test` unit harness
// (see `yarn test:unit` / tsconfig.unit.json). These guard the placement math
// (a reservation bar must span exactly its booked nights, clipped to the
// visible window) and the drag-drop drop-target math (a dropped card must land
// on a real room/day inside bounds — never off-grid). Getting either wrong
// would mis-draw occupancy or send a bad move to the backend.
import { addDaysISO, buildDayList } from './availabilityGrid';

export { addDaysISO, buildDayList };

// The three showcase densities. Each is a horizon (how many days the timeline
// spans) plus the per-day column width. Going day -> week -> month trades
// detail for overview; pinch-zoom crosses between them.
export type CalendarView = 'day' | 'week' | 'month';

export type ViewPreset = { view: CalendarView; days: number; dayWidth: number };

export const VIEW_PRESETS: Record<CalendarView, ViewPreset> = {
  day: { view: 'day', days: 1, dayWidth: 240 },
  week: { view: 'week', days: 7, dayWidth: 78 },
  month: { view: 'month', days: 31, dayWidth: 38 },
};

export const ROW_HEIGHT = 56;
export const ROOM_COL_WIDTH = 96;

// The five operator-facing cell statuses required by the showcase legend.
export type RoomCalStatus = 'available' | 'occupied' | 'cleaning' | 'out_of_order' | 'blocked';

const OOO_STATUSES = new Set(['out_of_order', 'out_of_service', 'maintenance', 'ooo', 'oos']);
const CLEANING_STATUSES = new Set(['dirty', 'cleaning', 'inspection', 'dirty_vacant']);

// Resolve a room's at-a-glance cell status from its own housekeeping/state
// field plus whether a reservation currently occupies it. Out-of-order and
// cleaning are room conditions that win over plain availability; an occupying
// reservation marks it dolu; otherwise it is müsait. `blocked` is supplied
// separately (per-day room blocks) by the caller via `cellStatusForDay`.
export function roomCalStatus(roomStatus: string | undefined, hasOccupancy: boolean): RoomCalStatus {
  const s = (roomStatus || '').toLowerCase();
  if (OOO_STATUSES.has(s)) return 'out_of_order';
  if (CLEANING_STATUSES.has(s)) return 'cleaning';
  if (hasOccupancy || s === 'occupied') return 'occupied';
  return 'available';
}

// Date-only (YYYY-MM-DD) from an ISO date or datetime. Returns undefined for
// blank / unparseable input so the caller skips that reservation rather than
// placing it at a garbage offset.
export function toDateOnly(input?: string): string | undefined {
  if (!input) return undefined;
  const m = input.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString().slice(0, 10);
}

// Whole-day difference b - a (both YYYY-MM-DD), anchored at local midnight so
// it is timezone-stable on any runner.
export function diffDays(a: string, b: string): number {
  const da = new Date(`${a}T00:00:00`).getTime();
  const db = new Date(`${b}T00:00:00`).getTime();
  return Math.round((db - da) / 86_400_000);
}

// A reservation reduced to exactly what the timeline needs. Structurally
// compatible with the real Reservation API type.
export type CalReservation = {
  id: string;
  room_id?: string;
  room_number?: string;
  guest_name?: string;
  status?: string;
  check_in?: string;
  check_out?: string;
  total_amount?: number;
  vip_status?: boolean;
};

// A reservation positioned on the grid: which room row, the start column, and
// how many columns it spans. `clippedStart/End` mark a stay that runs past the
// visible window edge so the bar can render a torn edge instead of lying about
// its length.
export type PlacedBar = {
  reservation: CalReservation;
  roomId: string;
  startOffset: number;
  nights: number;
  clippedStart: boolean;
  clippedEnd: boolean;
};

// Reservation statuses that no longer hold inventory and must not draw a bar.
const RELEASED_STATUSES = new Set(['cancelled', 'canceled', 'no_show', 'voided']);

export function isActiveReservation(status?: string): boolean {
  return !RELEASED_STATUSES.has((status || '').toLowerCase());
}

// Place every active, room-assigned reservation onto the visible window.
// Checkout day is exclusive (a stay 12->14 occupies the 12th and 13th), which
// matches how the night audit releases the room. Bars that fall entirely
// outside the window are dropped; bars that straddle an edge are clipped and
// flagged.
export function placeReservations(
  reservations: CalReservation[],
  dayList: string[],
): PlacedBar[] {
  if (dayList.length === 0) return [];
  const windowStart = dayList[0];
  const dayCount = dayList.length;
  const windowEndExcl = addDaysISO(dayList[dayCount - 1], 1);
  const bars: PlacedBar[] = [];
  for (const r of reservations) {
    if (!r.room_id) continue;
    if (!isActiveReservation(r.status)) continue;
    const ci = toDateOnly(r.check_in);
    const co = toDateOnly(r.check_out);
    if (!ci || !co) continue;
    if (co <= ci) continue;
    // Overlap test with an exclusive checkout day.
    if (!(ci < windowEndExcl && co > windowStart)) continue;
    const rawStart = diffDays(windowStart, ci);
    const rawEnd = diffDays(windowStart, co); // exclusive column
    const startOffset = Math.max(0, rawStart);
    const endOffset = Math.min(dayCount, rawEnd);
    const nights = Math.max(1, endOffset - startOffset);
    bars.push({
      reservation: r,
      roomId: r.room_id,
      startOffset,
      nights,
      clippedStart: rawStart < 0,
      clippedEnd: rawEnd > dayCount,
    });
  }
  return bars;
}

// Where a dragged card lands. Inputs are the card's starting grid position plus
// the gesture translation; output is clamped so the card can never leave the
// grid (day stays in [0, dayCount - nights], room stays in [0, roomCount - 1]).
export function computeDropTarget(args: {
  startOffset: number;
  startRoomIndex: number;
  dx: number;
  dy: number;
  dayWidth: number;
  rowHeight: number;
  dayCount: number;
  roomCount: number;
  nights: number;
}): { dayOffset: number; roomIndex: number; changedDay: boolean; changedRoom: boolean } {
  const rawDay = args.startOffset + Math.round(args.dx / args.dayWidth);
  const maxDay = Math.max(0, args.dayCount - args.nights);
  const dayOffset = Math.max(0, Math.min(maxDay, rawDay));
  const rawRoom = args.startRoomIndex + Math.round(args.dy / args.rowHeight);
  const roomIndex = Math.max(0, Math.min(Math.max(0, args.roomCount - 1), rawRoom));
  return {
    dayOffset,
    roomIndex,
    changedDay: dayOffset !== args.startOffset,
    changedRoom: roomIndex !== args.startRoomIndex,
  };
}

// Pinch result -> the density to settle on. Pinching OUT (scale > 1) zooms in
// toward day detail; pinching IN (scale < 1) zooms out toward the month
// overview. The thresholds give a deliberate, non-jittery single-step change.
const ZOOM_ORDER: CalendarView[] = ['month', 'week', 'day'];

export function nextViewFromZoom(current: CalendarView, scale: number): CalendarView {
  const i = ZOOM_ORDER.indexOf(current);
  if (i < 0) return current;
  if (scale >= 1.3 && i < ZOOM_ORDER.length - 1) return ZOOM_ORDER[i + 1];
  if (scale <= 0.77 && i > 0) return ZOOM_ORDER[i - 1];
  return current;
}

// Translate a confirmed drop into the backend operations needed. A room change
// becomes an assign-room call; a date shift becomes a check_in/check_out update
// that preserves the stay length. The component issues these against the real
// endpoints (RBAC + double-booking enforced server-side); a rejection reverts
// the card.
export type MovePlan = {
  assignRoomId?: string;
  newCheckIn?: string;
  newCheckOut?: string;
};

export function planMove(args: {
  changedRoom: boolean;
  changedDay: boolean;
  targetRoomId?: string;
  newCheckIn: string;
  nights: number;
}): MovePlan {
  const plan: MovePlan = {};
  if (args.changedRoom && args.targetRoomId) plan.assignRoomId = args.targetRoomId;
  if (args.changedDay) {
    plan.newCheckIn = args.newCheckIn;
    plan.newCheckOut = addDaysISO(args.newCheckIn, args.nights);
  }
  return plan;
}

export function hasMove(plan: MovePlan): boolean {
  return !!plan.assignRoomId || !!plan.newCheckIn;
}
