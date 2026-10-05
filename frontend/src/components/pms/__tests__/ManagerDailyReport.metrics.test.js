import { describe, expect, it } from 'vitest';
import { buildManagerDailyMetrics } from '../ManagerDailyReport';

describe('manager daily report metrics', () => {
  it('uses the selected business day and allocates stay revenue by night', () => {
    const result = buildManagerDailyMetrics({
      day: '2026-09-24',
      rooms: [{ id: 'r1' }, { id: 'r2' }, { id: 'r3', status: 'out_of_service' }],
      bookings: [
        { room_id: 'r1', status: 'checked_in', check_in: '2026-09-23', check_out: '2026-09-25', total_amount: 2000 },
        { room_id: 'r2', status: 'confirmed', check_in: '2026-09-24', check_out: '2026-09-25', total_amount: 800, channel: 'walk_in' },
        { room_id: 'r2', status: 'confirmed', check_in: '2026-09-26', check_out: '2026-09-27', total_amount: 900 },
      ],
    });

    expect(result).toMatchObject({
      totalRooms: 3,
      availableRooms: 2,
      occupiedRooms: 2,
      emptyRooms: 0,
      roomRevenue: 1800,
      adr: 900,
      revpar: 900,
      arrivals: 1,
      departures: 0,
      walkIns: 1,
    });
  });

  it('counts cancellations and no-shows only on their relevant date', () => {
    const result = buildManagerDailyMetrics({
      day: '2026-09-24',
      bookings: [
        { status: 'no_show', check_in: '2026-09-24', check_out: '2026-09-25' },
        { status: 'no_show', check_in: '2026-09-23', check_out: '2026-09-24' },
        { status: 'cancelled', check_in: '2026-09-30', check_out: '2026-10-01', cancelled_at: '2026-09-24T10:00:00Z' },
        { status: 'cancelled', check_in: '2026-09-30', check_out: '2026-10-01', cancelled_at: '2026-09-23T10:00:00Z' },
      ],
    });

    expect(result.noShows).toBe(1);
    expect(result.cancellations).toBe(1);
    expect(result.occupiedRooms).toBe(0);
  });
});
