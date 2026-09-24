import { describe, expect, it } from 'vitest';
import {
  assignmentReasonLabel,
  bookingSourceLabel,
  formatBookingAmount,
} from '@/components/VirtualizedBookingList';

describe('VirtualizedBookingList money presentation', () => {
  it('normalizes reservation sources and explains pending room assignment', () => {
    expect(bookingSourceLabel({ channel: 'ets' })).toBe('Etstur');
    expect(bookingSourceLabel({ booking_source: 'walkin' })).toBe('Walk-in');
    expect(bookingSourceLabel({ channel: 'seturapi' })).toBe('Setur');
    expect(assignmentReasonLabel({ room_type: 'Suite', auto_assignment_reason: 'no_available_room' }))
      .toBe('İçe aktarıldığı anda uygun oda bulunamadı');
    expect(assignmentReasonLabel({ room_id: 'room-1' })).toBe('');
  });
  it('formats TRY once without a duplicate dollar sign', () => {
    const value = formatBookingAmount(12262.5, 'TRY');
    expect(value).toContain('12.262,50');
    expect(value).toContain('₺');
    expect(value).not.toContain('$');
  });

  it('respects a reservation currency', () => {
    expect(formatBookingAmount(100, 'USD')).toContain('$');
    expect(formatBookingAmount(100, 'EUR')).toContain('€');
  });
});
