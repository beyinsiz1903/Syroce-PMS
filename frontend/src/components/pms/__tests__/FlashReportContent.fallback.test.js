import { describe, expect, it } from 'vitest';
import { buildFallbackFlashReport } from '../FlashReportContent';

describe('FlashReportContent fallback consistency', () => {
  it('allocates stay revenue to the selected day and includes dated ancillary charges', () => {
    const report = buildFallbackFlashReport({
      targetDate: '2026-09-24',
      rooms: [{ id: 'r1' }, { id: 'r2' }],
      bookings: [{
        id: 'b1',
        room_id: 'r1',
        status: 'checked_in',
        check_in: '2026-09-23',
        check_out: '2026-09-25',
        total_amount: 2000,
        paid_amount: 1000,
        charges: [
          { charge_category: 'food_beverage', amount: 120, business_date: '2026-09-24' },
          { charge_category: 'minibar', amount: 80, business_date: '2026-09-24' },
          { charge_category: 'laundry', amount: 50, business_date: '2026-09-23' },
        ],
      }],
    });

    expect(report.occupancy).toMatchObject({ occupied: 1, total: 2, available: 1 });
    expect(report.revenue).toMatchObject({ room: 1000, fb: 120, minibar: 80, laundry: 0, total: 1200, collected: 500, outstanding: 700 });
    expect(report.kpi).toMatchObject({ adr: 1000, revpar: 500 });
  });

  it('does not leak bookings or operational events from other dates', () => {
    const report = buildFallbackFlashReport({
      targetDate: '2026-09-24',
      rooms: [{ id: 'r1' }],
      bookings: [
        { status: 'confirmed', check_in: '2026-09-25', check_out: '2026-09-26', total_amount: 900 },
        { status: 'no_show', check_in: '2026-09-23', check_out: '2026-09-24' },
        { status: 'cancelled', check_in: '2026-09-24', check_out: '2026-09-25', cancelled_at: '2026-09-23' },
      ],
    });

    expect(report.occupancy.occupied).toBe(0);
    expect(report.revenue.total).toBe(0);
    expect(report.operations).toMatchObject({ arrivals: 0, departures: 0, no_shows: 0, cancellations: 0 });
  });
});
