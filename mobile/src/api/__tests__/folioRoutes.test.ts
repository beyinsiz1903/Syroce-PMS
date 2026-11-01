import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import test from 'node:test';
const source=readFileSync(resolve(process.cwd(),'src/api/folio.ts'),'utf8');
const screen=readFileSync(resolve(process.cwd(),'app/(departments)/folio/[id].tsx'),'utf8');
test('a payment preflight requests the normal fresh folio read, with encoded identity',()=>{
  assert.match(source,/encodeURIComponent\(folioId\).*fresh \? \{ nocache: true \}/);
  assert.match(screen,/getFolioById\(folioId, true\)/);
  assert.match(screen,/latest\.id !== folioId/);
});
test('folio read access never grants charge/payment operations and mutations recheck each permission',()=>{
  assert.match(screen,/mobileOperationAllowed\(user, 'post_charge'\)/);
  assert.match(screen,/mobileOperationAllowed\(user, 'post_payment'\)/);
  assert.match(screen,/freshWritableFolio\('post_charge'\)/);
  assert.match(screen,/freshWritableFolio\('post_payment'\)/);
});
test('folio payment retains currency, validates current balance and freezes retry identity',()=>{
  assert.match(screen,/currency: input\.currency/);
  assert.match(screen,/paymentAmountError\(amount, current\.balance\)/);
  assert.match(screen,/paymentAttemptForInput\(paymentKeyRef\.current/);
  assert.doesNotMatch(screen.slice(screen.indexOf('const openPaymentSheet'),screen.indexOf('const chargeAmountNum')),/paymentKeyRef\.current = null/);
});
test('folio UI never applies the TRY/zero formatter to an unknown or foreign amount',()=>{
  assert.doesNotMatch(screen,/formatCurrency\(/);
  assert.match(screen,/reservationAmountLabel\(value, currency\)/);
  assert.doesNotMatch(screen,/folio\?\.balance \?\? 0/);
});
