import { describe, expect, it } from 'vitest';
import { formatCancellationPolicy } from '../cancellationPolicy';

describe('cancellation policy display', () => {
  it('formats the structured agency contract policy without altering it', () => {
    const policy = Object.freeze({ free_until_days_before: 7, penalty_pct: 50, no_show_penalty_pct: 100 });
    expect(formatCancellationPolicy(policy)).toBe('Girişten 7 gün öncesine kadar ücretsiz iptal · İptal kesintisi: %50 · Gelmeme kesintisi: %100');
  });
  it('retains explicit zero terms and supported numeric strings', () => {
    expect(formatCancellationPolicy({ free_until_days_before: 0, penalty_pct: '0', no_show_penalty_pct: '0' })).toContain('0 gün');
    expect(formatCancellationPolicy({ penalty_pct: 0 })).toBe('İptal kesintisi: %0');
  });
  it.each([null, undefined, '', [], 5, false])('does not invent a flexible policy for %j', value => {
    expect(formatCancellationPolicy(value)).toBe('Belirtilmemiş');
  });
  it('does not invent omitted terms or coerce null/invalid fields to zero', () => {
    expect(formatCancellationPolicy({ penalty_pct: 50 })).toBe('İptal kesintisi: %50');
    expect(formatCancellationPolicy({ free_until_days_before: null, penalty_pct: '', no_show_penalty_pct: 101 })).toBe('Politika ayrıntıları doğrulanamadı');
    expect(formatCancellationPolicy({ free_until_days_before: 1.5, penalty_pct: {}, no_show_penalty_pct: true })).toBe('Politika ayrıntıları doğrulanamadı');
  });
  it.each([['flexible', 'Esnek'], ['non_refundable', 'İade Edilemez'], ['Özel anlaşma', 'Özel anlaşma']])('preserves legacy string %s', (value, label) => {
    expect(formatCancellationPolicy(value)).toBe(label);
  });
});
