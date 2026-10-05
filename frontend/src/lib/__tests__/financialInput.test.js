import { describe, expect, it } from 'vitest';

import {
  calculateFinancialLine,
  parseExchangeRate,
  parseMoney,
  parseQuantity,
  roundMoney,
} from '../financialInput';

describe('financial input contract', () => {
  it('accepts either decimal separator for money but never more than two decimals', () => {
    expect(parseMoney('150,74')).toBe(150.74);
    expect(parseMoney('150.74')).toBe(150.74);
    expect(parseMoney('150,741')).toBeNull();
  });

  it('keeps fractional quantities and exchange rates explicit', () => {
    expect(parseQuantity('1,250')).toBe(1.25);
    expect(parseExchangeRate('38,123456')).toBe(38.123456);
    expect(parseExchangeRate('38,1234567')).toBeNull();
  });

  it('rounds in the financial order: quantity, discount, tax, then conversion', () => {
    expect(calculateFinancialLine({
      unitAmount: '15,05', quantity: '3', discountAmount: '0,10', vatRate: '20', exchangeRate: '38,5',
    })).toMatchObject({
      subtotal: 45.15,
      discount: 0.1,
      net: 45.05,
      vat: 9.01,
      total: 54.06,
      accountingTotal: 2081.31,
    });
  });

  it('uses cents for familiar floating-point boundaries', () => {
    expect(roundMoney(0.1 + 0.2)).toBe(0.3);
  });
});
