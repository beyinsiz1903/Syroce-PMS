// Test koruması: roomOccupancyStatus, mobil grid yardımcısıyla aynı önceliği
// (occupied > blocked > free; OOO/OOS her şeyin önünde) uygular ve backend'in
// açık `occupancy_status` alanını yerelleştirilebilir `reason` metninden önce
// okur. Bu, web "Oda Bul" müsaitlik ekranının bloklu/dolu odaları yanlışlıkla
// "müsait" göstermesini engeller.
import { describe, it, expect } from 'vitest';
import {
  roomOccupancyStatus,
  normalizeOccupancyStatus,
  isBlockedRoomStatus,
  cellOccupancyStatus,
  getCellOccupancyTint,
} from '../calendarHelpers';

describe('normalizeOccupancyStatus', () => {
  it('bilinen değerleri normalize eder, boşluk/büyük-küçük harfe toleranslı', () => {
    expect(normalizeOccupancyStatus('free')).toBe('free');
    expect(normalizeOccupancyStatus(' Occupied ')).toBe('occupied');
    expect(normalizeOccupancyStatus('BLOCKED')).toBe('blocked');
  });

  it('bilinmeyen/boş değerlerde null döner (yedeğe düşülsün)', () => {
    expect(normalizeOccupancyStatus('rezerve')).toBeNull();
    expect(normalizeOccupancyStatus('')).toBeNull();
    expect(normalizeOccupancyStatus(undefined)).toBeNull();
  });
});

describe('isBlockedRoomStatus', () => {
  it('OOO/OOS/bakım durumlarını tanır', () => {
    expect(isBlockedRoomStatus('out_of_order')).toBe(true);
    expect(isBlockedRoomStatus('OOS')).toBe(true);
    expect(isBlockedRoomStatus('maintenance')).toBe(true);
    expect(isBlockedRoomStatus('available')).toBe(false);
    expect(isBlockedRoomStatus(undefined)).toBe(false);
  });
});

describe('roomOccupancyStatus', () => {
  it('açık occupancy_status alanını önceler', () => {
    expect(roomOccupancyStatus({ id: 'r1', available: false, occupancy_status: 'occupied' })).toBe('occupied');
    expect(roomOccupancyStatus({ id: 'r1', available: false, occupancy_status: 'blocked' })).toBe('blocked');
    expect(roomOccupancyStatus({ id: 'r1', occupancy_status: 'free' })).toBe('free');
  });

  it('OOO/OOS oda durumu her şeyin önünde gelir', () => {
    expect(
      roomOccupancyStatus({ id: 'r1', status: 'out_of_order', available: true, occupancy_status: 'free' }),
    ).toBe('blocked');
  });

  it('occupancy_status yoksa reason metnine düşer ("booked" -> occupied)', () => {
    expect(roomOccupancyStatus({ id: 'r1', available: false, reason: 'booked' })).toBe('occupied');
    expect(roomOccupancyStatus({ id: 'r1', available: false, reason: 'out_of_order' })).toBe('blocked');
  });

  it('yerelleştirilmiş reason ("rezerve") açık alan varsa doluluğu yanlış göstermez', () => {
    expect(
      roomOccupancyStatus({ id: 'r1', available: false, reason: 'rezerve', occupancy_status: 'occupied' }),
    ).toBe('occupied');
  });

  it('müsait oda free döner', () => {
    expect(roomOccupancyStatus({ id: 'r1', available: true })).toBe('free');
    expect(roomOccupancyStatus(null)).toBe('free');
  });
});

// Test koruması: cellOccupancyStatus, ana takvim ızgarasının her oda-gün
// hücresi için doluluk durumunu, roomOccupancyStatus ile AYNI önceliği
// (OOO/OOS her şeyin önünde, sonra occupied > blocked > free) izleyerek
// türetir. Böylece ızgara, "Oda Bul" ekranı ve mobil grid tutarlı renklenir.
describe('cellOccupancyStatus', () => {
  it('OOO/OOS oda durumu her şeyin önünde gelir (dolu olsa bile blocked)', () => {
    expect(
      cellOccupancyStatus({ covered: true, blocked: false, roomStatus: 'out_of_order' }),
    ).toBe('blocked');
    expect(
      cellOccupancyStatus({ covered: true, blocked: true, roomStatus: 'maintenance' }),
    ).toBe('blocked');
  });

  it('occupied, blocked önünde gelir (occupied > blocked)', () => {
    expect(cellOccupancyStatus({ covered: true, blocked: true })).toBe('occupied');
    expect(cellOccupancyStatus({ covered: true, blocked: false })).toBe('occupied');
  });

  it('rezervasyon yoksa aktif blok blocked döner', () => {
    expect(cellOccupancyStatus({ covered: false, blocked: true })).toBe('blocked');
  });

  it('rezervasyon/blok yoksa free döner', () => {
    expect(cellOccupancyStatus({ covered: false, blocked: false })).toBe('free');
    expect(cellOccupancyStatus({})).toBe('free');
    expect(cellOccupancyStatus()).toBe('free');
  });
});

describe('getCellOccupancyTint', () => {
  it('her duruma ayrı bir tint sınıfı verir, free dahil', () => {
    expect(getCellOccupancyTint('occupied')).toBe('bg-rose-100/40');
    expect(getCellOccupancyTint('blocked')).toBe('bg-slate-300/40');
    expect(getCellOccupancyTint('free')).toBe('bg-emerald-50/40');
  });

  it('bilinmeyen durumda boş string döner', () => {
    expect(getCellOccupancyTint('whatever')).toBe('');
    expect(getCellOccupancyTint()).toBe('');
  });
});
