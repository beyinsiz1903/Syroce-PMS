import assert from 'node:assert/strict';
import test from 'node:test';
import {
  effectiveRoomStatus,
  indexBookingsByRoomNumber,
  roomNumberKey,
  roomPresentation,
  cleaningElapsedMinutes,
  canConfirmRoomInspection,
} from '../roomPresentation';

test('in-house booking wins over a stale available room status', () => {
  assert.equal(effectiveRoomStatus('available', true), 'occupied');
  assert.equal(effectiveRoomStatus('dirty', true), 'occupied');
  assert.equal(effectiveRoomStatus('available', false), 'available');
});

test('maintenance takes precedence over occupancy and all housekeeping fields', () => {
  assert.equal(effectiveRoomStatus('maintenance', true), 'maintenance');
  assert.equal(effectiveRoomStatus(' OUT_OF_ORDER ', true), 'out_of_order');
  assert.deepEqual(roomPresentation({ status: 'available', housekeeping_status: 'maintenance' }, true), {
    occupancy: 'blocked', cleaning: 'blocked', blockedStatus: 'maintenance', isReady: false,
  });
  assert.equal(roomPresentation({ status: 'maintenance', room_status: 'inspected' }).isReady, false);
});

test('cleaning and occupancy remain separate; clean is awaiting inspection', () => {
  assert.deepEqual(roomPresentation({ status: 'dirty' }, true), {
    occupancy: 'occupied', cleaning: 'dirty', isReady: false,
  });
  assert.equal(roomPresentation({ status: 'clean' }).cleaning, 'inspection');
  assert.equal(roomPresentation({ status: 'inspected' }, true).isReady, false);
  assert.equal(roomPresentation({ status: 'available', current_booking_id: 'stay-1' }).isReady, false);
  assert.equal(roomPresentation({ status: 'available', housekeeping_status: 'dirty' }).isReady, false);
  assert.equal(roomPresentation({ status: 'available', housekeeping_status: 'clean' }).isReady, false);
  assert.equal(roomPresentation({ status: 'inspected' }).isReady, true);
});

test('open work prevents readiness even when the room document is stale', () => {
  assert.equal(roomPresentation({ status: 'available' }, false, [{ task_type: 'inspection', status: 'assigned' }]).cleaning, 'inspection');
  assert.equal(roomPresentation({ status: 'available' }, false, [{ task_type: 'cleaning', status: 'in_progress' }]).cleaning, 'cleaning');
  assert.equal(roomPresentation({ status: 'available' }, false, [{ task_type: 'maintenance', status: 'new' }]).isReady, false);
  assert.equal(roomPresentation({ status: 'inspected' }, false, [{ task_type: 'inspection', status: 'completed' }]).isReady, true);
  assert.equal(roomPresentation({ status: 'unrecognised' }).occupancy, 'unknown');
  assert.equal(roomPresentation({ status: 'unrecognised' }).isReady, false);
});

test('only supplied valid cleaning durations are displayed', () => {
  assert.equal(cleaningElapsedMinutes(24.9), 24);
  assert.equal(cleaningElapsedMinutes(0), 0);
  for (const value of [undefined, null, '30', -1, NaN, Infinity]) assert.equal(cleaningElapsedMinutes(value), null);
});

test('inspection confirmation refuses a newly blocked or occupied room', () => {
  assert.equal(canConfirmRoomInspection({ status: 'clean' }), true);
  assert.equal(canConfirmRoomInspection({ status: 'inspected' }), true);
  assert.equal(canConfirmRoomInspection({ status: 'maintenance', housekeeping_status: 'clean' }), false);
  assert.equal(canConfirmRoomInspection({ status: 'clean' }, true), false);
  assert.equal(canConfirmRoomInspection({ status: 'dirty' }), false);
  assert.equal(canConfirmRoomInspection({ status: 'cleaning' }), false);
});

test('bookings are joined to rooms with a normalised room number', () => {
  const booking = { id: 'stay-201', room_number: 201 };
  const index = indexBookingsByRoomNumber([booking]);
  assert.equal(index[roomNumberKey(' 201 ')], booking);
});
