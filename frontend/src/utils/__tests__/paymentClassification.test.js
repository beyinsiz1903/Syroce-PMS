import { describe, expect, it } from 'vitest';

import {
  classifyGuestPayment,
  guestPaymentClassificationLabel,
} from '@/utils/paymentClassification';

describe('guest payment classification', () => {
  it('classifies a partial collection as interim', () => {
    expect(classifyGuestPayment(250, 1000)).toBe('interim');
    expect(guestPaymentClassificationLabel(250, 1000)).toContain('Kısmi ödeme');
  });

  it('classifies a balance-closing collection as final', () => {
    expect(classifyGuestPayment(1000, 1000)).toBe('final');
    expect(classifyGuestPayment(999.995, 1000)).toBe('final');
    expect(guestPaymentClassificationLabel(1000, 1000)).toContain('Tam ödeme');
  });

  it('does not misclassify invalid amounts as final', () => {
    expect(classifyGuestPayment('', 1000)).toBe('interim');
    expect(classifyGuestPayment(-1, 1000)).toBe('interim');
    expect(guestPaymentClassificationLabel('', 1000)).toContain('Tutar girildiğinde');
  });
});
