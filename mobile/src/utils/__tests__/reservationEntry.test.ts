import test from 'node:test';
import assert from 'node:assert/strict';
import {reservationDateInput,reservationGuestCount,reservationRateInput} from '../reservationEntry';
test('reservation edits reject impossible dates and accept leap day without timezone changes',()=>{
  assert.equal(reservationDateInput('29.02.2028'),'2028-02-29');
  assert.equal(reservationDateInput('15/11/2026'),'2026-11-15');
  for(const input of ['31.02.2026','2026-02-29','2026-11-31','2026-00-10','2026-13-10','junk'])assert.equal(reservationDateInput(input),undefined);
});
test('guest edits never silently truncate fractions, exponents, trailing text or negative numbers',()=>{
  for(const value of ['2.5','2abc','2e1','-1','','51'])assert.equal(reservationGuestCount(value,1),null);
  assert.equal(reservationGuestCount('2',1),2);assert.equal(reservationGuestCount('0',0),0);
});
test('rate edits reject partial numeric parses and preserve explicit free accommodation',()=>{
  for(const value of ['100abc','1e3','Infinity','-1','1.234',''])assert.equal(reservationRateInput(value),null);
  assert.equal(reservationRateInput('0'),0);assert.equal(reservationRateInput('100,25'),100.25);
});
