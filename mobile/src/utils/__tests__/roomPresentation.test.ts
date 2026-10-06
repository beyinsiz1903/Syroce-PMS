import assert from 'node:assert/strict';
import test from 'node:test';
import {
  effectiveRoomStatus,
  indexBookingsByRoomNumber,
  roomNumberKey,
} from '../roomPresentation';

test('in-house booking wins over a stale available room status', () => {
  assert.equal(effectiveRoomStatus('available', true), 'occupied');
  assert.equal(effectiveRoomStatus('dirty', true), 'occupied');
  assert.equal(effectiveRoomStatus('available', false), 'available');
});

test('bookings are joined to rooms with a normalised room number', () => {
  const booking = { id: 'stay-201', room_number: 201 };
  const index = indexBookingsByRoomNumber([booking]);
  assert.equal(index[roomNumberKey(' 201 ')], booking);
});
