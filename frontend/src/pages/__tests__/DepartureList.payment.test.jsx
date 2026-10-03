import { describe, expect, it } from 'vitest';

import { isFinalPaymentWithinBalance } from '@/pages/DepartureList';

describe('DepartureList final payment validation', () => {
  it('accepts a partial or exact payment, but rejects an overpayment', () => {
    expect(isFinalPaymentWithinBalance(25, 100)).toBe(true);
    expect(isFinalPaymentWithinBalance(100, 100)).toBe(true);
    expect(isFinalPaymentWithinBalance(100.01, 100)).toBe(false);
    expect(isFinalPaymentWithinBalance(0, 100)).toBe(false);
  });
});
