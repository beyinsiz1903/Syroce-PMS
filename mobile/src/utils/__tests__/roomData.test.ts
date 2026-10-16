import assert from 'node:assert/strict';
import test from 'node:test';
import { loadRoomPages, RoomDataError, type RoomDataFailure, type RoomPageParams } from '../roomData';

const room = (id: number | string) => ({ id: String(id), room_number: String(id), status: 'available' });
const hasReason = (reason: RoomDataFailure) => (error: unknown) => error instanceof RoomDataError && error.reason === reason;

test('room inventory loads every page beyond the old 100/500 room limits', async () => {
  const records = Array.from({ length: 551 }, (_, index) => room(index));
  const calls: RoomPageParams[] = [];
  const result = await loadRoomPages(async (params) => {
    calls.push(params);
    return records.slice(params.offset, params.offset + params.limit);
  });
  assert.equal(result.length, 551);
  assert.equal(result.at(-1)?.id, '550');
  assert.deepEqual(calls, [0, 200, 400].map((offset) => ({ limit: 200, offset })));
});

test('a full final room page is followed by a completion probe; real empty lists remain empty', async () => {
  const offsets: number[] = [];
  assert.equal((await loadRoomPages(async ({ offset }) => {
    offsets.push(offset);
    return offset ? [] : [room(1), room(2)];
  }, { pageSize: 2 })).length, 2);
  assert.deepEqual(offsets, [0, 2]);
  assert.deepEqual(await loadRoomPages(async () => []), []);
  assert.deepEqual(await loadRoomPages(async () => ({ rooms: [room(1)] })), [room(1)]);
  assert.deepEqual(await loadRoomPages(async () => ({ items: [room(1)] })), [room(1)]);
});

test('malformed room pages and unsafe display fields fail instead of appearing empty', async () => {
  for (const invalid of [null, undefined, {}, { rooms: {} }, [null], [{}], [{ ...room(1), id: '' }],
    [{ ...room(1), room_number: 201 }], [{ ...room(1), status: {} }], [{ ...room(1), floor: {} }],
    [{ ...room(1), housekeeping: { assigned_to_name: {} } }], [{ ...room(1), housekeeping: { elapsed_minutes: -1 } }]]) {
    await assert.rejects(loadRoomPages(async () => invalid), hasReason('invalid_page'));
  }
  await assert.rejects(loadRoomPages(async () => [room(1), room(2), room(3)], { pageSize: 2 }), hasReason('invalid_page'));
});

test('repeated or duplicate room pages never resolve partial inventory', async () => {
  await assert.rejects(loadRoomPages(async () => [room(1), room(2)], { pageSize: 2 }), hasReason('duplicate_room'));
  await assert.rejects(loadRoomPages(async () => [room(1), room(1)]), hasReason('duplicate_room'));
  await assert.rejects(loadRoomPages(async ({ offset }) => offset ? {} : [room(1), room(2)], { pageSize: 2 }), hasReason('invalid_page'));
});

test('a later failure or safety cap cannot return earlier room pages', async () => {
  const failure = new Error('offline');
  await assert.rejects(loadRoomPages(async ({ offset }) => {
    if (offset) throw failure;
    return [room(1), room(2)];
  }, { pageSize: 2 }), (error) => error === failure);
  await assert.rejects(loadRoomPages(async ({ offset }) => [room(offset)], { pageSize: 1, maxPages: 2 }), hasReason('page_limit'));
});

test('invalid paging options fail before making a request', async () => {
  for (const options of [{ pageSize: 0 }, { pageSize: 2001 }, { maxPages: 0 }, { maxPages: 101 }]) {
    await assert.rejects(loadRoomPages(async () => { assert.fail('invalid options must not fetch'); }, options), hasReason('invalid_page'));
  }
});
