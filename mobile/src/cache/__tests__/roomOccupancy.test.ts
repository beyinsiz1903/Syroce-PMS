import assert from 'node:assert/strict';
import test from 'node:test';
import { invalidateRoomOccupancy } from '../roomOccupancy';

test('room movements refresh Today, Rooms and other occupancy consumers together', async () => {
  const keys: string[] = [];
  await invalidateRoomOccupancy({
    async invalidateQueries({ queryKey }) { keys.push(queryKey[0]); },
  });
  assert.deepEqual(keys, [
    'hub-today', 'frontdesk-inhouse-rooms', 'inhouse', 'frontdesk-rooms',
    'rooms', 'hk-inhouse', 'calendar', 'arrivals-today', 'departures-today',
  ]);
});
