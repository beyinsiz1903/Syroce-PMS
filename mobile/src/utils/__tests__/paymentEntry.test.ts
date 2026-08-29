import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parsePaymentAmount,
  paymentAmountError,
  paymentTypeForAmount,
} from '../paymentEntry.js';

test('parses Turkish decimal input and rejects invalid values', () => {
  assert.equal(parsePaymentAmount('1,25'), 1.25);
  assert.equal(parsePaymentAmount(' 6000 '), 6000);
  assert.equal(parsePaymentAmount('0'), null);
  assert.equal(parsePaymentAmount('abc'), null);
});

test('classifies full payment internally without asking the operator', () => {
  assert.equal(paymentTypeForAmount(250, 1000), 'interim');
  assert.equal(paymentTypeForAmount(1000, 1000), 'final');
  assert.equal(paymentTypeForAmount(1000.004, 1000), 'final');
});

test('prevents accidental overpayment', () => {
  assert.equal(paymentAmountError(1000, 1000), null);
  assert.equal(paymentAmountError(1000.01, 1000), 'overpayment');
  assert.equal(paymentAmountError(null, 1000), 'invalid');
});
