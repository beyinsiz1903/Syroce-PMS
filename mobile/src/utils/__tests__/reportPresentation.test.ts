import assert from 'node:assert/strict';
import test from 'node:test';
import { financeShareText, postedRoomKpis, reportAmountLabel, reportArLabel, reportCountLabel, reportCurrencyBuckets, reportMoneyTotalsLabel, reportPercentLabel, reportRowTotals, reportTotalsLabel } from '../reportPresentation';

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

test('folio totals preserve currencies, real zero and unavailable balances', () => {
  const text = reportMoneyTotalsLabel({ EUR: 80.25, TRY: 100.49 }, null);
  assert.match(text, /€.*80,25/);
  assert.match(text, /₺.*100,49/);
  assert.equal(reportMoneyTotalsLabel(undefined, null, 'TRY'), '—');
  assert.match(reportMoneyTotalsLabel({}, undefined, 'EUR'), /€.*0,00/);
  assert.equal(reportMoneyTotalsLabel(undefined, 100, undefined), '—');
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

test('multi-currency booked value, ADR and company balances are not a synthetic TRY total', () => {
  assert.match(reportTotalsLabel({ EUR: 120, USD: 200 }), /€.*120,00.*\$.*200,00/);
  assert.equal(reportTotalsLabel(null), '—');
  assert.equal(reportTotalsLabel(undefined), '—');
  assert.equal(reportTotalsLabel({}), 'Kayıt yok');
  assert.equal(reportPercentLabel(null), '—'); // Backend deliberately returns null when FX is incomplete.
  assert.equal(reportPercentLabel(0), '%0.0');
});

test('expense aggregates keep currency rows separate; missing prices/currency are not zero TRY', () => {
  const totals = reportRowTotals([{ currency: 'EUR', amount: 10 }, { currency: 'USD', total_amount: 20 }, { currency: 'EUR', amount: 15 }, { amount: 100 }]);
  assert.deepEqual(totals, { EUR: 25, USD: 20, UNKNOWN: 100 });
  assert.equal(reportTotalsLabel(totals).includes('₺'), false);
  assert.ok(Number.isNaN(reportRowTotals([{ currency: 'EUR' }]).EUR));
});

test('GM ADR/RevPAR use posted Flash room KPIs in the same business day, not collections or booked forecasts', () => {
  const flash = { date: '2026-10-26', revenue: { basis: 'posted_folio_charges_plus_untransferred_pos', adr_by_currency: { EUR: 60, USD: 100 }, rev_par_by_currency: { EUR: 30, USD: 50 }, posting_pending: true } };
  assert.match(postedRoomKpis(flash, '2026-10-26').adr, /€.*60,00.*\$.*100,00/);
  assert.equal(postedRoomKpis(flash, '2026-11-01').adr, '—');
  assert.equal(postedRoomKpis({ ...flash, revenue: { basis: 'collected_payments', adr_by_currency: { TRY: 1000 } } }).adr, '—');
  assert.equal(postedRoomKpis(undefined).revpar, '—');
  assert.equal(postedRoomKpis(flash).postingPending, true);
});

test('screen and share use the same currency buckets and actual PMS business day, not the segment date filter', () => {
  const snapshot = { business_date: '2026-10-26', report_date: '2026-11-01',
    pending_ar: { complete: false, by_currency: { EUR: { total: 120 }, USD: { total: 200 } } },
    mtd_collections: { amount: 300, currency: 'USD', conversion_issue_count: 1 } };
  const share = financeShareText(snapshot);
  assert.ok(share.includes(reportArLabel(snapshot.pending_ar.by_currency)));
  assert.match(share, /2026-10-26/);
  assert.doesNotMatch(share, /2026-11-01|₺/);
  assert.match(share, /eksik kaynak/);
  assert.match(share, /kısmi/);
  assert.match(financeShareText({}), /Bekleyen alacak: —/);
});
