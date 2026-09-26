import { describe, expect, it } from 'vitest';

import {
  buildCityLedgerCandidateAccount,
  getCityLedgerPaymentAllocations,
  validateCityLedgerPayment,
  validateCityLedgerPaymentAllocations,
} from '@/pages/CityLedgerAccounts';

describe('CityLedgerAccounts payment guards', () => {
  it('prefills a city-ledger account from a pending company', () => {
    expect(buildCityLedgerCandidateAccount({
      source_company_id: 'company-1',
      company_name: 'Örnek Acente',
      account_name: 'Örnek Acente',
      contact_person: 'Zeliha',
      payment_terms: '45',
    })).toMatchObject({
      source_company_id: 'company-1',
      company_name: 'Örnek Acente',
      account_name: 'Örnek Acente',
      contact_person: 'Zeliha',
      payment_terms: 45,
      billing_country: 'Türkiye',
    });
  });

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

  it('builds a payment allocation only for rooms with a positive entered amount', () => {
    const rooms = [{ booking_id: 'booking-101', open_amount: 100 }, { booking_id: 'booking-102', open_amount: 50 }];
    expect(getCityLedgerPaymentAllocations(rooms, { 'booking-101': '25', 'booking-102': '' })).toEqual([
      { booking_id: 'booking-101', amount: 25 },
    ]);
  });

  it('allows a general payment when no room is selected', () => {
    expect(validateCityLedgerPaymentAllocations('50', [{ booking_id: 'booking-101', open_amount: 50 }], {})).toBeNull();
  });

  it('rejects a room allocation whose total differs from the payment', () => {
    expect(validateCityLedgerPaymentAllocations(
      '50',
      [{ booking_id: 'booking-101', open_amount: 100 }],
      { 'booking-101': '49.99' },
    )).toBe('Oda bazlı dağıtım toplamı ödeme tutarına eşit olmalıdır');
  });

  it('rejects an allocation over the selected room balance', () => {
    expect(validateCityLedgerPaymentAllocations(
      '51',
      [{ booking_id: 'booking-101', open_amount: 50 }],
      { 'booking-101': '51' },
    )).toBe('Bir odaya ayrılan tahsilat o odanın açık bakiyesini aşamaz');
  });
});
