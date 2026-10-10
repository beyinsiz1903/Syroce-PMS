import { describe, expect, it } from 'vitest';

import { roomsFromResponse } from '@/pages/MinibarPage';

describe('MinibarPage room response contract', () => {
  it('uses the bare list returned by the canonical PMS rooms endpoint', () => {
    const rooms = [{ id: 'room-101', room_number: '101' }];

    expect(roomsFromResponse(rooms)).toEqual(rooms);
  });

  it('remains compatible with previously wrapped room responses', () => {
    expect(roomsFromResponse({ rooms: [{ id: 'room-102' }] })).toEqual([{ id: 'room-102' }]);
    expect(roomsFromResponse({ items: [{ id: 'room-103' }] })).toEqual([{ id: 'room-103' }]);
    expect(roomsFromResponse({ rooms: 'invalid' })).toEqual([]);
  });
});
