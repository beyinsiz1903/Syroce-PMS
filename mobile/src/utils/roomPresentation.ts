export type RoomOccupancyBooking = {
  room_number?: unknown;
};

export function roomNumberKey(value: unknown): string {
  return String(value ?? '').trim();
}

export function indexBookingsByRoomNumber<T extends RoomOccupancyBooking>(bookings: T[]): Record<string, T> {
  const result: Record<string, T> = {};
  for (const booking of bookings) {
    const key = roomNumberKey(booking.room_number);
    if (key) result[key] = booking;
  }
  return result;
}

/** A checked-in stay is the occupancy source of truth even if housekeeping
 * has not yet synchronised the room document from available -> occupied. */
export function effectiveRoomStatus(status: unknown, hasInHouseBooking: boolean): string {
  const normalised = normaliseRoomStatus(status);
  if (isBlockedStatus(normalised)) return normalised;
  if (hasInHouseBooking) return 'occupied';
  return normalised;
}

export type RoomPresentationSource = {
  status?: unknown;
  room_status?: unknown;
  housekeeping_status?: unknown;
  hk_status?: unknown;
  current_booking_id?: unknown;
};

type PresentationTask = { status?: string; task_type?: string };
export type RoomOccupancy = 'vacant' | 'occupied' | 'blocked' | 'unknown';
export type RoomCleaning = 'dirty' | 'cleaning' | 'inspection' | 'inspected' | 'ready' | 'blocked' | 'unknown';
export type RoomPresentation = {
  occupancy: RoomOccupancy;
  cleaning: RoomCleaning;
  blockedStatus?: 'maintenance' | 'out_of_order';
  isReady: boolean;
};

export function normaliseRoomStatus(status: unknown): string {
  return String(status ?? '').trim().toLowerCase();
}

function isBlockedStatus(status: string): status is 'maintenance' | 'out_of_order' {
  return status === 'maintenance' || status === 'out_of_order';
}

/** Occupancy and housekeeping are independent. A clean room still needs an
 * inspection; an inspected occupied room is never advertised as sellable. */
export function roomPresentation(
  room: RoomPresentationSource,
  hasInHouseBooking = false,
  tasks: PresentationTask[] = [],
): RoomPresentation {
  const status = normaliseRoomStatus(room.status);
  const statuses = [status, room.room_status, room.housekeeping_status, room.hk_status].map(normaliseRoomStatus);
  const blockedStatus = statuses.includes('out_of_order')
    ? 'out_of_order'
    : statuses.includes('maintenance') ? 'maintenance' : undefined;
  if (blockedStatus) return { occupancy: 'blocked', cleaning: 'blocked', blockedStatus, isReady: false };

  const occupancy: RoomOccupancy = hasInHouseBooking || !!roomNumberKey(room.current_booking_id) || status === 'occupied'
    ? 'occupied'
    : ['available', 'dirty', 'cleaning', 'clean', 'inspection', 'inspected'].includes(status) ? 'vacant' : 'unknown';
  const openTasks = tasks.filter((task) => !['completed', 'done', 'cancelled', 'verified', 'closed'].includes(normaliseRoomStatus(task.status)));
  const activeCleaning = openTasks.some((task) => normaliseRoomStatus(task.task_type) === 'cleaning' && normaliseRoomStatus(task.status) === 'in_progress');
  const inspectionPending = openTasks.some((task) => normaliseRoomStatus(task.task_type) === 'inspection');
  const hk = normaliseRoomStatus(room.housekeeping_status) || normaliseRoomStatus(room.hk_status)
    || normaliseRoomStatus(room.room_status) || status;
  let cleaning: RoomCleaning = 'unknown';
  if (activeCleaning || hk === 'cleaning') cleaning = 'cleaning';
  else if (hk === 'dirty') cleaning = 'dirty';
  else if (inspectionPending || hk === 'inspection') cleaning = 'inspection';
  else if (hk === 'inspected' || (status === 'inspected' && ['available', 'clean', 'inspected'].includes(hk))) cleaning = 'inspected';
  else if (hk === 'clean') cleaning = 'inspection';

  // Any unfinished room task (including maintenance) prevents a ready claim.
  const isReady = occupancy === 'vacant' && cleaning === 'inspected' && openTasks.length === 0;
  return { occupancy, cleaning: isReady ? 'ready' : cleaning, isReady };
}

/** The room endpoint supplies actual elapsed cleaning time separately from
 * task creation time. Queue age must never be presented as cleaning duration. */
export function cleaningElapsedMinutes(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
}

export function canConfirmRoomInspection(room: RoomPresentationSource, hasInHouseBooking = false, tasks: PresentationTask[] = []): boolean {
  const state = roomPresentation(room, hasInHouseBooking, tasks);
  return state.occupancy === 'vacant' && ['inspection', 'inspected', 'ready'].includes(state.cleaning);
}
