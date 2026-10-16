import assert from 'node:assert/strict';
import test from 'node:test';
import { reportAmountLabel, reportCountLabel, reportCurrencyBuckets } from '../reportPresentation';

test('reports preserve actual zero but never invent a missing or invalid count', () => {
  assert.equal(reportCountLabel(0), '0');
  assert.equal(reportCountLabel(12), '12');
  for (const value of [undefined, null, '', '0', false, -1, 1.5, NaN, Infinity]) {
    assert.equal(reportCountLabel(value), '—');
  }
});

test('collection amounts require both an explicit API amount and currency', () => {
  assert.match(reportAmountLabel(0, 'TRY'), /0,00/);
  assert.match(reportAmountLabel(125, 'EUR'), /€/);
  for (const currency of [undefined, null, '', 'EURO']) assert.equal(reportAmountLabel(125, currency), '—');
  for (const amount of [undefined, null, '', '0', false, NaN, Infinity]) assert.equal(reportAmountLabel(amount, 'EUR'), '—');
});

test('missing currency breakdown remains unknown; an explicit empty map is a real empty state', () => {
  assert.deepEqual(reportCurrencyBuckets(undefined), { kind: 'unavailable', buckets: [] });
  assert.deepEqual(reportCurrencyBuckets(null), { kind: 'unavailable', buckets: [] });
  assert.deepEqual(reportCurrencyBuckets([]), { kind: 'unavailable', buckets: [] });
  assert.deepEqual(reportCurrencyBuckets({}), { kind: 'empty', buckets: [] });
});

test('AR currency buckets stay separate and invalid entries never turn into TRY or zero', () => {
  assert.deepEqual(reportCurrencyBuckets({ EUR: { total: 150 }, USD: { total: 200 }, TRY: { total: 0 } }), {
    kind: 'data', buckets: [{ currency: 'EUR', total: 150 }, { currency: 'USD', total: 200 }, { currency: 'TRY', total: 0 }],
  });
  assert.deepEqual(reportCurrencyBuckets({ EURO: { total: 75 }, EUR: { total: null }, USD: null }), {
    kind: 'data', buckets: [{ currency: undefined, total: 75 }, { currency: 'EUR', total: undefined }, { currency: 'USD', total: undefined }],
  });
});
