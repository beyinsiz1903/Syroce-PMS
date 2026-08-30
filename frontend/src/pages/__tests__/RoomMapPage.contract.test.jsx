import { describe, expect, it } from 'vitest';

import { statusMeta, summarizeRoomMap } from '../RoomMapPage';

describe('RoomMapPage operational contract', () => {
  it('does not show a room as occupied from a stale room status alone', () => {
    expect(statusMeta('occupied', false).label).toBe('Müsait');
    expect(statusMeta('clean', true).label).toBe('Dolu');
  });

  it('summarizes reservation occupancy separately from housekeeping state', () => {
    expect(summarizeRoomMap([
      { id: '1', status: 'occupied' },
      { id: '2', status: 'clean', booking: { booking_id: 'booking-2' } },
      { id: '3', status: 'dirty' },
      { id: '4', status: 'maintenance' },
      { id: '5', status: 'blocked' },
      { id: '6', status: 'cleaning' },
    ], [{ booking_id: 'unassigned-1' }])).toEqual({
      total: 6,
      occupied: 1,
      available: 1,
      dirty: 1,
      unassigned: 1,
    });
  });
});
