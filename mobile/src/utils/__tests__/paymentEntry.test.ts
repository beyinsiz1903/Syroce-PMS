import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parsePaymentAmount,
  paymentAmountError,
  paymentTypeForAmount,
  paymentAttemptForInput,
} from '../paymentEntry.js';

test('parses Turkish decimal input and rejects invalid values', () => {
  assert.equal(parsePaymentAmount('1,25'), 1.25);
  assert.equal(parsePaymentAmount(' 6000 '), 6000);
  assert.equal(parsePaymentAmount('0'), null);
  assert.equal(parsePaymentAmount('abc'), null);
  assert.equal(parsePaymentAmount('0.004'), null);
  assert.equal(parsePaymentAmount('1e3'), null);
  assert.equal(parsePaymentAmount('1.234'), null);
  assert.equal(parsePaymentAmount('Infinity'), null);
});

test('a lost response retry freezes its key and type when the server balance changes', () => {
  const input = { bookingId: 'stay-1', currency: 'TRY', amount: 400, method: 'card' as const, balance: 800 };
  const first = paymentAttemptForInput(null, input, () => 'original-key');
  const retry = paymentAttemptForInput(first, { ...input, balance: 400 }, () => 'must-not-be-used');
  assert.equal(first.paymentType, 'interim');
  assert.equal(retry, first);
  assert.equal(retry.key, 'original-key');
  assert.equal(retry.paymentType, 'interim');
  assert.equal(paymentAttemptForInput(first, { ...input, balance: 0 }, () => 'must-not-be-used'), first);
  assert.equal(paymentAttemptForInput(first, { ...input, method: 'cash' }, () => 'new-intent-key').key, 'new-intent-key');
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
  assert.equal(paymentAmountError(NaN, 1000), 'invalid');
  assert.equal(paymentAmountError(1, undefined), 'unknown_balance');
  assert.equal(paymentAmountError(1, NaN), 'unknown_balance');
  assert.equal(paymentAmountError(1, 0), 'no_balance');
  assert.equal(paymentAmountError(1, -5), 'no_balance');
});
