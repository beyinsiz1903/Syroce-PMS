// Test koruması: parseBookingConflict yardımcısı backend'in structured 409
// payload'ını doğru tanır, eski/plain 409'ları sessizce reddeder ve diğer
// hata sınıflarına dokunmaz. BookingConflictDialog'un tüm 3 call site'ı
// (RoomsTab quick-booking + ReservationCalendar + PMSModule) bu parser'ın
// `null` vs structured ayrımına göre dialog vs toast'a düşer.
import { describe, it, expect } from 'vitest';
import { parseBookingConflict } from '@/lib/bookingConflict';

const makeError = (status, data) => ({ response: { status, data } });

describe('parseBookingConflict', () => {
  it('structured 409: tüm alanları unpack eder', () => {
    const err = makeError(409, {
      detail: {
        message: 'Oda 101 bu tarihlerde dolu',
        conflicting_booking_id: 'bk-123',
        conflict_type: 'room_double_book',
        conflict_window: {
          room_id: 'room-1',
          check_in: '2026-06-01',
          check_out: '2026-06-03',
        },
      },
    });
    const result = parseBookingConflict(err);
    expect(result).toEqual({
      message: 'Oda 101 bu tarihlerde dolu',
      conflictingBookingId: 'bk-123',
      conflictType: 'room_double_book',
      conflictWindow: {
        room_id: 'room-1',
        check_in: '2026-06-01',
        check_out: '2026-06-03',
      },
    });
  });

  it('structured 409: sadece conflicting_booking_id varsa da kabul eder (window yok)', () => {
    const err = makeError(409, {
      detail: { conflicting_booking_id: 'bk-9' },
    });
    const result = parseBookingConflict(err);
    expect(result).not.toBeNull();
    expect(result.conflictingBookingId).toBe('bk-9');
    expect(result.conflictType).toBe('booking'); // default
    expect(result.message).toMatch(/zaten dolu/);
    expect(result.conflictWindow).toBeNull();
  });

  it('plain-string 409 (legacy): null döner → caller toast fallback yapar', () => {
    const err = makeError(409, { detail: 'Bu oda meşgul' });
    expect(parseBookingConflict(err)).toBeNull();
  });

  it('detail objesi var ama conflict alanı yok: null döner', () => {
    const err = makeError(409, { detail: { foo: 'bar' } });
    expect(parseBookingConflict(err)).toBeNull();
  });

  it('non-409 (400/500/422): null döner — yanlış statüde dialog açılmaz', () => {
    expect(parseBookingConflict(makeError(400, { detail: { conflicting_booking_id: 'x' } }))).toBeNull();
    expect(parseBookingConflict(makeError(500, { detail: { conflicting_booking_id: 'x' } }))).toBeNull();
    expect(parseBookingConflict(makeError(422, { detail: { conflicting_booking_id: 'x' } }))).toBeNull();
  });

  it('detail tamamen yok: null döner', () => {
    expect(parseBookingConflict(makeError(409, {}))).toBeNull();
    expect(parseBookingConflict(makeError(409, null))).toBeNull();
  });

  it('error nesnesi/response yok: crash etmeden null döner', () => {
    expect(parseBookingConflict(null)).toBeNull();
    expect(parseBookingConflict(undefined)).toBeNull();
    expect(parseBookingConflict({})).toBeNull();
    expect(parseBookingConflict(new Error('network'))).toBeNull();
  });
});
