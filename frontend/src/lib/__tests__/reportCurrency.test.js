import { describe, expect, it } from 'vitest';
import { currencyBreakdownEntries, formatCurrencyBreakdown, isMixedCurrencyBreakdown } from '../reportCurrency';

describe('formatCurrencyBreakdown', () => {
  it('renders mixed currencies independently', () => {
    const value = formatCurrencyBreakdown({ USD: 120, EUR: 100 }, 220, 'TRY', 'tr-TR');
    expect(value).toContain('100');
    expect(value).toContain('€');
    expect(value).toContain('120');
    expect(value).toContain('$');
    expect(value).toContain('EUR:');
    expect(value).toContain('USD:');
    expect(value).not.toContain('₺');
  });

  it('uses the fallback currency for legacy single-currency payloads', () => {
    expect(formatCurrencyBreakdown({}, 250, 'EUR', 'tr-TR')).toContain('€');
  });

  it('exposes sorted entries for an explicit multi-currency presentation', () => {
    const entries = currencyBreakdownEntries({ TRY: 670441, EUR: 635.48, USD: 0 }, 'tr-TR');

    expect(entries.map((entry) => entry.currency)).toEqual(['EUR', 'TRY']);
    expect(entries[0].formatted).toContain('€');
    expect(entries[1].formatted).toContain('₺');
    expect(isMixedCurrencyBreakdown({ TRY: 1, EUR: 1 })).toBe(true);
    expect(isMixedCurrencyBreakdown({ TRY: 1, EUR: 0 })).toBe(false);
  });
});
