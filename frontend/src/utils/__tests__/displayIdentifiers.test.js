import { describe, expect, it } from 'vitest';
import { folioLabel, guestLabel, reservationLabel, roomLabel } from '../displayIdentifiers';

describe('displayIdentifiers', () => {
  it('uses readable values instead of internal identifiers', () => {
    expect(roomLabel({ room_id: 'e33d0d2f-2170-46f9-a8ba-9e6f7b4b0cc8', room_number: '107' })).toBe('107');
    expect(reservationLabel({ booking_id: 'e33d0d2f-2170-46f9-a8ba-9e6f7b4b0cc8', reservation_number: 'RES-107' })).toBe('RES-107');
    expect(folioLabel({ folio_id: 'e33d0d2f-2170-46f9-a8ba-9e6f7b4b0cc8', folio_number: 'F-55' })).toBe('F-55');
    expect(guestLabel({ guest_id: 'e33d0d2f-2170-46f9-a8ba-9e6f7b4b0cc8', guest_name: 'Ada Yılmaz' })).toBe('Ada Yılmaz');
  });

  it('never renders an identifier as a fallback', () => {
    const record = { room_id: 'room-uuid', booking_id: 'booking-uuid', folio_id: 'folio-uuid', guest_id: 'guest-uuid' };
    expect(roomLabel(record)).toBe('Oda bilgisi yok');
    expect(reservationLabel(record)).toBe('Rezervasyon kaydı');
    expect(folioLabel(record)).toBe('Folyo kaydı');
    expect(guestLabel(record)).toBe('Misafir');
  });
});
