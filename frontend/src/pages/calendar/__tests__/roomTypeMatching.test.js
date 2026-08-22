import { describe, expect, it } from 'vitest';

import {
  compactGuestName,
  formatGuestName,
  normalizeRoomType,
  roomIsFreeForBooking,
  roomMatchesBookingType,
} from '../roomTypeMatching';

describe('room type matching', () => {
  it('tamamen kucuk veya buyuk yazilan misafir adlarini okunur gosterir', () => {
    expect(formatGuestName('yusuf ünal')).toBe('Yusuf Ünal');
    expect(formatGuestName('DERİN BERK BABACAN')).toBe('Derin Berk Babacan');
    expect(formatGuestName('McDonald Smith')).toBe('McDonald Smith');
  });

  it('dar takvim kartinda anlamsiz uc nokta yerine ad ve soyad bas harfini gosterir', () => {
    expect(compactGuestName('Ahmet Mehmet Yılmaz', 10)).toBe('Ahmet Y.');
    expect(compactGuestName('Derin Berk Babacan', 10)).toBe('Derin B.');
    expect(compactGuestName('Mustafa Tosun', 20)).toBe('Mustafa Tosun');
  });

  it('Türkçe karakter ve büyük/küçük harf farklarını normalize eder', () => {
    expect(normalizeRoomType('  Jakuzisiz AĞAÇ Ev ')).toBe('jakuzisiz agac ev');
    expect(roomMatchesBookingType(
      { room_type: 'Jakuzisiz Ağaç Ev' },
      { room_type_id: 'jakuzisiz ağaç ev' },
    )).toBe(true);
  });

  it('oda tipi eşleşmeyen fiziksel odayı aday göstermez', () => {
    expect(roomMatchesBookingType(
      { room_type: 'Suit Oda' },
      { room_type: 'Standart Oda' },
    )).toBe(false);
  });

  it('çakışan rezervasyonu olan odayı uygun saymaz', () => {
    const room = { id: 'room-1', room_type: 'Standart Oda' };
    const booking = { id: 'new', check_in: '2026-08-22', check_out: '2026-08-24' };
    expect(roomIsFreeForBooking(room, booking, [
      { id: 'old', room_id: 'room-1', check_in: '2026-08-23', check_out: '2026-08-25', status: 'confirmed' },
    ])).toBe(false);
    expect(roomIsFreeForBooking(room, booking, [
      { id: 'old', room_id: 'room-1', check_in: '2026-08-23', check_out: '2026-08-25', status: 'cancelled' },
    ])).toBe(true);
  });
});
