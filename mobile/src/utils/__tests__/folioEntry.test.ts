import test from 'node:test';
import assert from 'node:assert/strict';
import { folioEntrySummary, folioWriteAttempt } from '../folioEntry';

const folio = { id:'f1', status:'open', currency:'EUR', balance:850, charges:[{total:1000,currency:'EUR'},{total:999,currency:'EUR',voided:true}], payments:[{amount:200,currency:'EUR',status:'paid'},{amount:50,currency:'EUR',payment_type:'refund'},{amount:900,currency:'EUR',status:'failed'}] };
test('folio amounts preserve EUR and exclude voided charges/failed payments; refunds reduce collections',()=>{
  assert.deepEqual(folioEntrySummary(folio),{currency:'EUR',balance:850,currencyConflict:false,chargesTotal:1000,paymentsTotal:150,writable:true});
});
test('missing/null/invalid balance never becomes a settled zero or a writable folio',()=>{
  for(const balance of [undefined,null,'',NaN,Infinity,false])assert.equal(folioEntrySummary({...folio,balance}).writable,false);
  assert.equal(folioEntrySummary({...folio,balance:0}).balance,0);
  assert.equal(folioEntrySummary({...folio,status:'closed'}).writable,false);
  assert.equal(folioEntrySummary({...folio,currency:undefined}).writable,false);
});
test('mixed or invalid movement currency blocks a scalar payment rather than summing currencies',()=>{
  for(const currency of ['USD','bad currency','']){
    const summary=folioEntrySummary({...folio,charges:[{total:1000,currency}]});
    assert.equal(summary.writable,false);assert.equal(summary.balance,undefined);assert.equal(summary.chargesTotal,undefined);
  }
});
test('legacy folio-owned charges without a currency retain the explicit folio denomination',()=>{
  assert.equal(folioEntrySummary({...folio,charges:[{total:1000}]}).chargesTotal,1000);
});
test('uncertain write retries reuse a key; changing amount/method/category creates a new intent',()=>{
  const input={folioId:'f1',amount:200,method:'cash',currency:'EUR'};
  const first=folioWriteAttempt(null,input,()=> 'key1');
  assert.equal(folioWriteAttempt(first,input,()=> 'unused'),first);
  assert.equal(folioWriteAttempt(first,{...input,amount:300},()=> 'key2').key,'key2');
  assert.equal(folioWriteAttempt(first,{...input,method:'card'},()=> 'key3').key,'key3');
});
