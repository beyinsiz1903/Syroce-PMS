import { describe, it, expect } from 'vitest';
import { formatCurrency, currencySymbol, localeForCurrency, formatAmount } from '@/lib/currency';

describe('currency.formatCurrency', () => {
  it('TRY varsayılanı: undefined currency → ₺ sembolü ile döner', () => {
    const out = formatCurrency(1500);
    expect(out).toMatch(/1\.500/);
    expect(out).toMatch(/₺|TRY/);
  });

  it('USD: doğru sembol/locale uygular', () => {
    const out = formatCurrency(99.5, 'USD');
    expect(out).toMatch(/99/);
    expect(out).toMatch(/\$|USD/);
  });

  it('EUR: doğru locale ile decimal döner', () => {
    const out = formatCurrency(12.34, 'EUR');
    expect(out).toMatch(/12/);
    expect(out).toMatch(/€|EUR/);
  });

  it('1000 üzeri: opts vermezsen decimals=0 olur (compact mode)', () => {
    const out = formatCurrency(2500, 'TRY');
    expect(out).not.toMatch(/[.,]00/);
  });

  it('1000 altı: 2 ondalık basamak görünür', () => {
    const out = formatCurrency(99.5, 'TRY');
    expect(out).toMatch(/99[.,]50/);
  });

  it('null/undefined/NaN değerler 0 olarak fallback', () => {
    expect(formatCurrency(null)).toMatch(/0/);
    expect(formatCurrency(undefined)).toMatch(/0/);
    expect(formatCurrency(NaN)).toMatch(/0/);
    expect(formatCurrency('abc')).toMatch(/0/);
  });

  it('boş currency → TRY default (regression: $ → TRY fix digitalocean.md)', () => {
    const out = formatCurrency(100, '');
    expect(out).toMatch(/₺|TRY/);
    expect(out).not.toContain('$');
  });

  it('opts.decimals override edilebilir', () => {
    const out = formatCurrency(1234.567, 'USD', { decimals: 3 });
    expect(out).toMatch(/567/);
  });

  it('lowercase currency code: case-insensitive çalışır', () => {
    const out = formatCurrency(100, 'try');
    expect(out).toMatch(/₺|TRY/);
  });
});

describe('currency.currencySymbol', () => {
  it('bilinen kod: doğru sembol', () => {
    expect(currencySymbol('TRY')).toBe('₺');
    expect(currencySymbol('USD')).toBe('$');
    expect(currencySymbol('EUR')).toBe('€');
  });

  it('bilinmeyen kod: kodun kendisini döner', () => {
    expect(currencySymbol('XYZ')).toBe('XYZ');
  });

  it('null/undefined → TRY sembolü fallback', () => {
    expect(currencySymbol(null)).toBe('₺');
    expect(currencySymbol(undefined)).toBe('₺');
  });
});

describe('currency.localeForCurrency', () => {
  it('TRY → tr-TR', () => {
    expect(localeForCurrency('TRY')).toBe('tr-TR');
  });
  it('bilinmeyen → tr-TR fallback', () => {
    expect(localeForCurrency('XYZ')).toBe('tr-TR');
  });
});

describe('currency.formatAmount', () => {
  it('para birimi sembolü olmadan sadece sayı döner', () => {
    const out = formatAmount(1234.5, 'TRY');
    expect(out).toMatch(/1\.234/);
    expect(out).not.toContain('₺');
  });
});
