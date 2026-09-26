import { describe, expect, it } from 'vitest';
import { applyRoomSwap } from '../calendarHelpers';

describe('applyRoomSwap', () => {
  it('moves both reservations to the opposite room without mutating the originals', () => {
    const source = { id: 'source', room_id: 'room-107', guest_name: 'Murat' };
    const target = { id: 'target', room_id: 'room-205', guest_name: 'Enes' };
    const untouched = { id: 'other', room_id: 'room-103' };
    const bookings = [source, target, untouched];

    const result = applyRoomSwap(bookings, source, target);

    expect(result).toEqual([
      { ...source, room_id: 'room-205' },
      { ...target, room_id: 'room-107' },
      untouched,
    ]);
    expect(source.room_id).toBe('room-107');
    expect(target.room_id).toBe('room-205');
    expect(result[2]).toBe(untouched);
  });

  it('leaves state unchanged when swap data is incomplete', () => {
    const bookings = [{ id: 'source', room_id: 'room-107' }];
    expect(applyRoomSwap(bookings, bookings[0], null)).toBe(bookings);
  });
});
