// Pure helpers for the reservation "change room" panel. Kept free of React /
// network imports so they run under the plain `node:test` unit harness (see
// `yarn test:unit` / tsconfig.unit.json). These guard the availability filter
// that prevents the panel from offering already-booked rooms (double-booking).

// ISO date / datetime string -> YYYY-MM-DD for the availability query. Returns
// undefined for blank / unparseable input so the caller can bail out instead of
// querying with a bad window.
export function isoDateOnly(input?: string): string | undefined {
  if (!input) return undefined;
  const m = input.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString().slice(0, 10);
}

// Keep only rooms the backend reports as genuinely free for the window
// (available === true). Anything else — false, undefined, or missing — is
// excluded so a booked / unknown room can never be offered for assignment.
export function filterAvailableRooms<T extends { available?: boolean }>(rooms: T[]): T[] {
  return rooms.filter((r) => r.available === true);
}

// Decides what the room panel renders from the raw availability rooms plus the
// in-flight flag. Single source of truth for the loading / empty / list states
// so the component stays a thin renderer over this tested logic.
export type RoomPanelView<T> =
  | { kind: 'loading' }
  | { kind: 'empty' }
  | { kind: 'list'; rooms: T[] };

export function roomPanelView<T extends { available?: boolean }>(
  rooms: T[],
  loading: boolean,
): RoomPanelView<T> {
  if (loading) return { kind: 'loading' };
  const available = filterAvailableRooms(rooms);
  if (available.length === 0) return { kind: 'empty' };
  return { kind: 'list', rooms: available };
}
