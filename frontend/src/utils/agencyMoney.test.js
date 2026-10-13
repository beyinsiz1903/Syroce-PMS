import { expect, it } from 'vitest';
import { currencyTotalsText } from './agencyMoney';
it('groups currencies without conversion', () => {
  const text = currencyTotalsText([{ currency: 'TRY', amount: 1000 }, { currency: 'EUR', amount: 100 }], 'amount');
  expect(text).toContain('1.000'); expect(text).toContain('100,00'); expect(text).not.toContain('1.100');
});
it('does not label missing currency as TRY', () => {
  expect(currencyTotalsText([{ amount: 50 }], 'amount')).toContain('para birimi eksik');
});
