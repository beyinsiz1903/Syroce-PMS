import { describe, expect, it } from 'vitest';

import { validateCityLedgerPayment } from '@/pages/CityLedgerAccounts';

describe('CityLedgerAccounts payment guards', () => {
  it('accepts a finite payment within the outstanding balance', () => {
    expect(validateCityLedgerPayment('4.25', 10)).toBeNull();
  });

  it.each([
    ['', 10],
    ['0', 10],
    ['-1', 10],
    ['not-a-number', 10],
  ])('rejects invalid payment amount %s', (amount, balance) => {
    expect(validateCityLedgerPayment(amount, balance)).toBe('Geçerli bir ödeme tutarı girin');
  });

  it.each([0, -1, Number.NaN])('rejects an invalid outstanding balance %s', (balance) => {
    expect(validateCityLedgerPayment('1', balance)).toBe('Bu hesabın ödenecek bakiyesi bulunmuyor');
  });

  it('rejects payment above the outstanding balance', () => {
    expect(validateCityLedgerPayment('10.01', 10)).toBe('Ödeme tutarı açık bakiyeyi aşamaz');
  });
});
