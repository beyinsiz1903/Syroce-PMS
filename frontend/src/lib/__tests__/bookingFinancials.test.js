import { describe, expect, it } from 'vitest';
import { bookingFinancials, normalizeCurrencyCode } from '@/lib/bookingFinancials';

describe('bookingFinancials', () => {
  it('uses the authoritative folio balance so extras are not hidden', () => {
    expect(bookingFinancials(
      { total_amount: 1000, paid_amount: 200, currency: 'TL' },
      [{ balance: 950 }],
    )).toEqual({ total: 1150, paid: 200, balance: 950, currency: 'TRY' });
  });

  it('supports the financial aliases returned by front desk endpoints', () => {
    expect(bookingFinancials({
      total_charges: 1350,
      payments_total: 400,
      balance_due: 950,
      currency_code: 'EUR',
    })).toEqual({ total: 1350, paid: 400, balance: 950, currency: 'EUR' });
  });

  it('respects an explicit zero balance instead of recalculating stale totals', () => {
    expect(bookingFinancials({
      total_amount: 1000,
      paid_amount: 200,
      folio_balance: 0,
    }).balance).toBe(0);
  });

  it('normalizes the Turkish lira aliases', () => {
    expect(normalizeCurrencyCode('TL')).toBe('TRY');
    expect(normalizeCurrencyCode('₺')).toBe('TRY');
  });
});
