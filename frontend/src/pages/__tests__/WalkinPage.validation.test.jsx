import { describe, expect, it } from 'vitest';

import { clampWalkinNights, validateWalkinCheckin } from '@/pages/WalkinPage';

describe('WalkinPage validation', () => {
  it('keeps the stay length in the supported range', () => {
    expect(clampWalkinNights(0)).toBe(1);
    expect(clampWalkinNights(7)).toBe(7);
    expect(clampWalkinNights(99)).toBe(14);
  });

  it('rejects invalid guest counts and overpayments', () => {
    const valid = { adults: 1, children: 0, totalAmount: 500, paymentAmount: 500, paymentMethod: 'card' };
    expect(validateWalkinCheckin(valid)).toBeNull();
    expect(validateWalkinCheckin({ ...valid, adults: 0 })).toBe('Yetişkin sayısı en az 1 olmalı');
    expect(validateWalkinCheckin({ ...valid, children: -1 })).toBe('Çocuk sayısı negatif olamaz');
    expect(validateWalkinCheckin({ ...valid, paymentAmount: 501 })).toBe('Ödenen tutar toplam tutarı aşamaz');
  });
});
