import { describe, expect, it } from 'vitest';

import { buildCalendarRateLookup } from '../calendarHelpers';


describe('buildCalendarRateLookup', () => {
  it('uses Syroce configured daily rates and ignores reservation amounts', () => {
    const lookup = buildCalendarRateLookup([
      {
        pms_room_type: 'Jakuzisiz ağaç ev',
        rate_plan_code: 'standard',
        dates: [{ date: '2026-08-29', rate: 7500 }],
      },
    ]);

    expect(lookup['Jakuzisiz ağaç ev|2026-08-29']).toBe(7500);
  });

  it('shows the lowest configured rate when several plans share one header', () => {
    const lookup = buildCalendarRateLookup([
      {
        pms_room_type: 'standard',
        dates: [{ date: '2026-08-29', rate: 5000 }],
      },
      {
        pms_room_type: 'standard',
        dates: [{ date: '2026-08-29', rate: 4250 }],
      },
    ]);

    expect(lookup['standard|2026-08-29']).toBe(4250);
  });

  it('does not create a rate for missing or invalid local calendar values', () => {
    const lookup = buildCalendarRateLookup([
      {
        pms_room_type: 'standard',
        dates: [
          { date: '2026-08-29', rate: null },
          { date: '2026-08-30', rate: 0 },
        ],
      },
    ]);

    expect(lookup).toEqual({});
  });
});
