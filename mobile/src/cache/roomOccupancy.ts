// A successful room movement must invalidate both tabs, not just the screen
// which performed it. Keep these keys shared with reservation edits as well.
export async function invalidateRoomOccupancy(client: {
  invalidateQueries: (filters: { queryKey: readonly string[] }) => Promise<unknown>;
}): Promise<void> {
  await Promise.all([
    'hub-today', 'frontdesk-inhouse-rooms', 'inhouse', 'frontdesk-rooms',
    'rooms', 'hk-inhouse', 'calendar', 'arrivals-today', 'departures-today',
  ].map((key) => client.invalidateQueries({ queryKey: [key] })));
}
