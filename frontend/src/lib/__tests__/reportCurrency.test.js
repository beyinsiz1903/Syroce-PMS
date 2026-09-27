import { describe, expect, it } from 'vitest';
import { formatCurrencyBreakdown } from '../reportCurrency';

describe('formatCurrencyBreakdown', () => {
  it('renders mixed currencies independently', () => {
    const value = formatCurrencyBreakdown({ USD: 120, EUR: 100 }, 220, 'TRY', 'tr-TR');
    expect(value).toContain('100');
    expect(value).toContain('€');
    expect(value).toContain('120');
    expect(value).toContain('$');
    expect(value).not.toContain('₺');
  });

  it('uses the fallback currency for legacy single-currency payloads', () => {
    expect(formatCurrencyBreakdown({}, 250, 'EUR', 'tr-TR')).toContain('€');
  });
});
