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
  if (hasInHouseBooking) return 'occupied';
  return String(status ?? '').toLowerCase();
}
