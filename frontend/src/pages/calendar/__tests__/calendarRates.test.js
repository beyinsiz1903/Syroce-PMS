import { describe, expect, it } from 'vitest';

import {
  buildCalendarRateLookup,
  getCalendarRoomNightRate,
  getCalendarStayTotal,
} from '../calendarHelpers';


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

  it('prefills the quick booking nightly price from the room board date', () => {
    const room = { room_type: 'standard', base_price: 150 };
    const rates = { 'standard|2026-09-05': 4300 };

    expect(getCalendarRoomNightRate(rates, room, '2026-09-05')).toBe(4300);
    expect(getCalendarRoomNightRate(rates, room, '2026-09-06')).toBe(150);
  });

  it('sums daily room-board rates for a multi-night quick booking', () => {
    const room = { room_type: 'standard', base_price: 150 };
    const rates = {
      'standard|2026-09-05': 4300,
      'standard|2026-09-06': 4600,
      'standard|2026-09-07': 5000,
    };

    expect(getCalendarStayTotal(rates, room, '2026-09-05', '2026-09-08')).toBe(13900);
  });
});
