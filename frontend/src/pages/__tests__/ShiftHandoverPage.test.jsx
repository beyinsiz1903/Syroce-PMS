import { describe, expect, it } from 'vitest';

import { isSameShiftTransfer } from '@/pages/ShiftHandoverPage';

describe('ShiftHandoverPage validation', () => {
  it('rejects handovers to the same shift', () => {
    expect(isSameShiftTransfer('afternoon', 'afternoon')).toBe(true);
    expect(isSameShiftTransfer('afternoon', 'night')).toBe(false);
  });
});
