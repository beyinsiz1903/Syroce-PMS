import { describe, expect, it } from 'vitest';

import { canReturnLostFoundItem, hasLostFoundMatchCriteria } from '@/pages/LostFoundPage';

describe('LostFoundPage chain-of-custody validation', () => {
  it('requires a matched guest before an item can be returned', () => {
    expect(canReturnLostFoundItem({ status: 'claimed' })).toBe(false);
    expect(canReturnLostFoundItem({ status: 'stored', guest_name: 'Ayşe Yılmaz' })).toBe(false);
    expect(canReturnLostFoundItem({ status: 'claimed', guest_name: 'Ayşe Yılmaz' })).toBe(true);
  });

  it('does not submit a guest match with no identifying criterion', () => {
    expect(hasLostFoundMatchCriteria({ guest_name: ' ', guest_contact: '', booking_id: '' })).toBe(false);
    expect(hasLostFoundMatchCriteria({ booking_id: 'booking-42' })).toBe(true);
  });
});
