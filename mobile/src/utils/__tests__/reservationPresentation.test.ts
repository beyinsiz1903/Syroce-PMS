import assert from 'node:assert/strict';
import test from 'node:test';
import {
  reservationMoneySummary,
  reservationStatusLabel,
  reservationAmountLabel,
  reservationCollectedAmount,
  reservationCurrency,
  reservationSourceLabel,
  paymentMethodLabel,
  paymentStatusLabel,
  hasSeparatePayer,
} from '../reservationPresentation';

test('reservation statuses are presented in Turkish', () => {
  assert.equal(reservationStatusLabel('checked_in'), 'Giriş yaptı');
  assert.equal(reservationStatusLabel('confirmed'), 'Onaylı');
});

test('server full-stay summary wins over partially posted nights', () => {
  assert.deepEqual(
    reservationMoneySummary({
      summaryTotal: 5000,
      summaryBalance: 3500,
      bookingTotal: 5000,
      rateBase: 5000,
      folioBalance: 500,
      charges: [{ total: 2000 }],
      payments: [{ amount: 1500 }],
    }),
    { total: 5000, paid: 1500, balance: 3500 },
  );
});

test('charge totals include tax, exclude voids and do not invent a balance', () => {
  assert.deepEqual(
    reservationMoneySummary({
      charges: [{ amount: 400, total: 450 }, { total: 50 }, { total: 999, voided: true }],
      payments: [{ amount: 75 }],
    }),
    { total: 500, paid: 75, balance: undefined },
  );
});

test('missing, blank, boolean and invalid values remain unknown while explicit zero stays zero', () => {
  for (const value of [undefined, null, '', ' ', false, true, 'abc', NaN, Infinity]) {
    assert.deepEqual(reservationMoneySummary({ bookingTotal: value, bookingBalance: value, bookingCollected: value }), { total: undefined, paid: undefined, balance: undefined });
  }
  assert.deepEqual(reservationMoneySummary({ bookingTotal: 0, bookingBalance: 0, payments: [] }), { total: 0, paid: 0, balance: 0 });
  assert.deepEqual(reservationMoneySummary({ rateBase: 900 }), { total: undefined, paid: undefined, balance: undefined });
});

test('net collections follow backend rules for transfers, discounts, invalid payments and refunds', () => {
  assert.equal(reservationCollectedAmount([
    { amount: 1000, method: 'card', status: 'paid', currency: 'EUR' },
    { amount: 100, method: 'cash', status: 'refunded', currency: 'EUR' },
    { amount: 50, payment_type: 'refund', currency: 'EUR' },
    { amount: 400, method: 'city_ledger' },
    { amount: 400, payment_type: 'city_ledger_transfer' },
    { amount: 20, method: 'discount' },
    { amount: 100, status: 'pending' },
    { amount: 100, status: 'failed' },
    { amount: 100, voided: true },
  ], 'EUR'), 850);
  assert.equal(reservationCollectedAmount(undefined, 'EUR'), undefined);
  assert.equal(reservationCollectedAmount([{ amount: null }], 'EUR'), undefined);
  assert.equal(reservationCollectedAmount([{ amount: 100, currency: 'USD' }], 'EUR'), undefined);
});

test('currency and absent amount labels do not silently assume Turkish lira or paid', () => {
  assert.equal(reservationCurrency(' eur '), 'EUR');
  assert.equal(reservationCurrency(''), undefined);
  assert.equal(reservationCurrency('EURO'), undefined);
  assert.match(reservationAmountLabel(20, 'EUR'), /€/);
  assert.equal(reservationAmountLabel(undefined, 'EUR'), 'Bilgi yok');
  assert.match(reservationAmountLabel(20), /para birimi belirtilmemiş/);
});

test('source and payment labels preserve meaningful Turkish states', () => {
  assert.equal(reservationStatusLabel(''), 'Durum belirtilmemiş');
  assert.equal(reservationSourceLabel('phone'), 'Telefon');
  assert.equal(reservationSourceLabel('Booking.com'), 'Booking.com');
  assert.equal(reservationSourceLabel(undefined), 'Kaynak belirtilmemiş');
  assert.equal(paymentMethodLabel('city_ledger'), 'Cari hesaba aktarım');
  assert.equal(paymentStatusLabel({ status: 'paid', voided: true }), 'İptal edildi');
  assert.equal(paymentStatusLabel({ status: 'refunded' }), 'İade');
  assert.equal(paymentStatusLabel({ payment_type: 'refund', status: 'pending' }), 'Bekliyor');
  assert.equal(paymentStatusLabel({ payment_type: 'refund', status: 'failed' }), 'Başarısız');
  assert.equal(paymentStatusLabel({ payment_type: 'refund', status: 'cancelled' }), 'İptal edildi');
});

test('guest collection is not based on an agency/company or ambiguous aggregate balance', () => {
  assert.equal(hasSeparatePayer({ folios: [{ folio_type: 'guest', status: 'open' }] }), false);
  assert.equal(hasSeparatePayer({ folios: [] }), false);
  assert.equal(hasSeparatePayer({}), true);
  assert.equal(hasSeparatePayer({ folios: [{ status: 'open' }] }), true);
  assert.equal(hasSeparatePayer({ folios: [{ folio_type: 'agency' }] }), true);
  assert.equal(hasSeparatePayer({ folios: [{ folio_type: 'guest', payor_type: 'company' }] }), true);
  assert.equal(hasSeparatePayer({ agency_id: 'a1', folios: [] }), true);
  assert.equal(hasSeparatePayer({ channel: 'agency', folios: [] }), true);
  assert.equal(hasSeparatePayer({ ota_channel: 'Booking.com', folios: [] }), true);
  assert.equal(hasSeparatePayer({ ota_channel: 'Booking.com', payment_model: 'hotel_collect', folios: [] }), false);
  assert.equal(hasSeparatePayer({ payment_model: 'merchant', folios: [] }), true);
  assert.equal(hasSeparatePayer({ folios: [{ folio_type: 'guest', status: 'open' }, { folio_type: 'guest', status: 'open' }] }), true);
});
