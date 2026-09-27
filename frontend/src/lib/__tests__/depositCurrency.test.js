import { describe, expect, it } from 'vitest';
import {
  depositTotalsByCurrency,
  formatDepositTotals,
  normalizeDepositCurrency
} from '../depositCurrency';

describe('deposit currency helpers', () => {
  it('normalizes the legacy TL currency code', () => {
    expect(normalizeDepositCurrency('TL')).toBe('TRY');
    expect(normalizeDepositCurrency('eur')).toBe('EUR');
  });

  it('keeps mixed-currency deposit totals separate', () => {
    const totals = depositTotalsByCurrency([
      { amount: 100, refunded_amount: 20, currency: 'EUR' },
      { amount: 40, currency: 'EUR' },
      { amount: 50, currency: 'USD' }
    ], row => row.amount - (row.refunded_amount || 0));

    expect(totals).toEqual([['EUR', 120], ['USD', 50]]);
    expect(formatDepositTotals(totals, 'tr-TR')).toContain('€120,00');
    expect(formatDepositTotals(totals, 'tr-TR')).toContain('$50,00');
  });
});
