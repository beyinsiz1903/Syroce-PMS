import { describe, expect, it } from 'vitest';
import { cashierCalendarDay, formatCashierTime, formatCashierTimestamp } from '../cashierTime';

describe('cashier UTC instants rendered in labelled Türkiye time, never business-day conversion', () => {
  it.each(['2026-10-31T16:34:54.123456', '2026-10-31T16:34:54Z', '2026-10-31T16:34:54+00:00', '2026-10-31T19:34:54+03:00', '2026-10-31 16:34:54'])('converts %s once', value => {
    expect(formatCashierTimestamp(value)).toBe('31.10.2026 19:34');
    expect(formatCashierTime(value)).toBe('19:34');
    expect(formatCashierTimestamp(value, { seconds: true })).toBe('31.10.2026 19:34:54');
  });
  it('rolls date forward at midnight and does not use the machine timezone', () => {
    expect(formatCashierTimestamp('2026-10-31T22:05:00Z')).toBe('01.11.2026 01:05');
    expect(cashierCalendarDay(new Date('2026-10-31T22:05:00Z'))).toBe('2026-11-01');
  });
  it.each([null, undefined, '', 'invalid', '2026-10-26'])('does not invent an instant for %s', value => {
    expect(formatCashierTimestamp(value)).toBe('—');
    expect(formatCashierTime(value)).toBe('—');
  });
});
