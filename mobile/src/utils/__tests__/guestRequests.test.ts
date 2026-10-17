import assert from 'node:assert/strict';
import test from 'node:test';
import { filterRoomRequests, parseRoomRequestDetail, parseRoomRequests, roomRequestCategory, roomRequestPath } from '../guestRequests';

const room = (id = 'r1', unread = 1) => ({ room_id: id, room_number: '201', unread, total: 2, last_body: 'İlave havlu', last_created_at: '2026-10-17T10:00:00Z' });
const message = (id = 'm1', roomId = 'r1') => ({ id, room_id: roomId, body: 'İlave havlu', sender_type: 'guest', read: false, created_at: '2026-10-17T10:00:00Z' });

test('room inbox excludes non-room WhatsApp threads and counts only visible unread requests', () => {
  const result = parseRoomRequests({ threads: [room('r1', 2), room('wa_905000000000', 8), room('r2', 0)], total_unread: 10 });
  assert.deepEqual(result.threads.map(row => row.room_id), ['r1', 'r2']);
  assert.equal(result.total_unread, 2);
});
test('empty streams are valid; broken contracts and duplicate rooms are never an empty success', () => {
  assert.deepEqual(parseRoomRequests({ threads: [] }), { threads: [], total_unread: 0 });
  for (const value of [null, {}, { conversations: [] }, { threads: {} }, { threads: [null] },
    { threads: [room(), room()] }, { threads: [{ ...room(), unread: -1 }] },
    { threads: [{ ...room(), room_number: 201 }] }, { threads: [{ ...room(), last_body: {} }] }]) {
    assert.throws(() => parseRoomRequests(value));
  }
});
test('rooms sort by recent activity without reordering the original response', () => {
  const threads = [room('old'), { ...room('new'), last_created_at: '2026-10-18T10:00:00Z' }];
  assert.deepEqual(parseRoomRequests({ threads }).threads.map(row => row.room_id), ['new', 'old']);
  assert.equal(threads[0].room_id, 'old');
});
test('room and Turkish request searches combine with unread filtering', () => {
  const threads = [room('r1'), { ...room('r2', 0), room_number: '202', last_body: 'Teknik servis' }];
  assert.equal(filterRoomRequests(threads, ' 201 ', false)[0].room_id, 'r1');
  assert.equal(filterRoomRequests(threads, 'İLAVE', true).length, 1);
  assert.equal(filterRoomRequests(threads, '202', true).length, 0);
});
test('thread validation enforces the selected room for both envelope and every message', () => {
  for (const value of [null, { room_id: 'r2', messages: [] }, { room_id: 'r1', messages: [message('m1', 'r2')] },
    { room_id: 'r1', messages: [{ ...message(), body: {} }] }, { room_id: 'r1', messages: [message(), message()] },
    { room_id: 'r1', messages: [{ ...message(), sender_type: 'personnel' }] }]) {
    assert.throws(() => parseRoomRequestDetail(value, 'r1'));
  }
});
test('guest requests and hotel replies are returned chronologically with request metadata', () => {
  const guest = { ...message(), request_id: 'qr1', category: 'rooms', priority: 'high' };
  const staff = { ...message('m2'), sender_type: 'staff', created_at: '2026-10-17T10:05:00Z' };
  const result = parseRoomRequestDetail({ room_id: 'r1', room_number: '201', messages: [staff, guest] }, 'r1');
  assert.deepEqual(result.messages.map(row => row.id), ['m1', 'm2']);
  assert.equal(result.messages[0].request_id, 'qr1');
});
test('room identifiers are safely encoded and cannot target WhatsApp contacts', () => {
  assert.equal(roomRequestPath('r/1?test=x'), '/api/messaging/guest-requests/threads/r%2F1%3Ftest%3Dx');
  assert.throws(() => roomRequestPath(''));
  assert.throws(() => roomRequestPath('wa_905000000000'));
  assert.equal(roomRequestCategory('rooms'), 'Oda / Temizlik');
  assert.equal(roomRequestCategory('unknown_internal_key'), 'Misafir talebi');
});
