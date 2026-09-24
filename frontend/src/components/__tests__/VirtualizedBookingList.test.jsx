import { describe, expect, it } from 'vitest';
import { formatBookingAmount } from '@/components/VirtualizedBookingList';

describe('VirtualizedBookingList money presentation', () => {
  it('formats TRY once without a duplicate dollar sign', () => {
    const value = formatBookingAmount(12262.5, 'TRY');
    expect(value).toContain('12.262,50');
    expect(value).toContain('₺');
    expect(value).not.toContain('$');
  });

  it('respects a reservation currency', () => {
    expect(formatBookingAmount(100, 'USD')).toContain('$');
    expect(formatBookingAmount(100, 'EUR')).toContain('€');
  });
});
