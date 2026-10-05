import { describe, expect, it } from 'vitest';
import { calculateBookingStats } from '@/lib/bookingStats';

describe('calculateBookingStats', () => {
  it('keeps mixed-currency totals and averages separate', () => {
    expect(calculateBookingStats([
      { status: 'confirmed', total_amount: 1000, currency: 'TRY' },
      { status: 'checked_in', total_amount: 500, currency_code: 'TL' },
      { status: 'pending', total_amount: 100, currency: 'EUR' },
    ])).toEqual({
      total: 3,
      confirmed: 1,
      checkedIn: 1,
      revenueByCurrency: { TRY: 1500, EUR: 100 },
      adrByCurrency: { TRY: 750, EUR: 100 },
    });
  });

  it('defaults missing currencies to TRY without losing zero-valued bookings', () => {
    expect(calculateBookingStats([
      { status: 'pending', total_amount: 0 },
      { status: 'pending', total_amount: 250 },
    ])).toMatchObject({
      revenueByCurrency: { TRY: 250 },
      adrByCurrency: { TRY: 125 },
    });
  });
});
