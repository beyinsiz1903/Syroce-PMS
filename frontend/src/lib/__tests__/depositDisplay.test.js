import { describe, expect, it } from 'vitest';
import { depositGuestLabel, formatDepositDate } from '../depositDisplay';

describe('deposit display helpers', () => {
  it('does not render a blank guest cell', () => {
    expect(depositGuestLabel({ guest_name: '' })).toBe('Misafir bilgisi eksik');
    expect(depositGuestLabel({ guest_name: '  Ayşe Yılmaz  ' })).toBe('Ayşe Yılmaz');
  });

  it('localizes valid dates and explains missing or invalid dates', () => {
    expect(formatDepositDate('2026-10-01T09:15:00Z', 'tr-TR')).toMatch(/2026/);
    expect(formatDepositDate()).toBe('Tarih bilgisi yok');
    expect(formatDepositDate('not-a-date')).toBe('Geçersiz tarih');
  });
});
