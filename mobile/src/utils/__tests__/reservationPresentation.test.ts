import assert from 'node:assert/strict';
import test from 'node:test';
import {
  reservationMoneySummary,
  reservationStatusLabel,
} from '../reservationPresentation';

test('reservation statuses are presented in Turkish', () => {
  assert.equal(reservationStatusLabel('checked_in'), 'Giriş yaptı');
  assert.equal(reservationStatusLabel('confirmed'), 'Onaylı');
});

test('folio values win and a legacy zero total falls back to the real rate', () => {
  assert.deepEqual(
    reservationMoneySummary({
      bookingTotal: 0,
      bookingPaid: 0,
      rateBase: 5000,
      rateTotal: 0,
      folioBalance: 3500,
      payments: [{ amount: 1500 }],
    }),
    { total: 5000, paid: 1500, balance: 3500 },
  );
});

test('folio charges establish the displayed total', () => {
  assert.deepEqual(
    reservationMoneySummary({
      bookingTotal: 100,
      charges: [{ amount: 400 }, { total: 50 }],
      payments: [{ amount: 75 }],
    }),
    { total: 450, paid: 75, balance: 375 },
  );
});
