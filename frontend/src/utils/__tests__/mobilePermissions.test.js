import { describe, expect, it } from 'vitest';

import {
  canAdjustMobileInventory,
  canApproveMobileRequest,
  canUpdateMobileOrderStatus,
} from '@/utils/mobilePermissions';

describe('mobile role permissions', () => {
  it.each([
    [{ role: 'super_admin' }, true],
    [{ roles: ['front_desk', 'finance_manager'] }, true],
    [{ role: 'staff' }, false],
    [null, false],
  ])('guards approval actions for %o', (user, expected) => {
    expect(canApproveMobileRequest(user)).toBe(expected);
  });

  it.each([
    [{ role: 'super_admin' }, true],
    [{ roles: ['front_desk', 'warehouse'] }, true],
    [{ role: 'service' }, false],
    [undefined, false],
  ])('guards stock adjustment for %o', (user, expected) => {
    expect(canAdjustMobileInventory(user)).toBe(expected);
  });

  it('supports primary and secondary roles without granting unrelated staff', () => {
    expect(canUpdateMobileOrderStatus({ role: 'super_admin' }, 'ready')).toBe(true);
    expect(canUpdateMobileOrderStatus({ roles: ['staff', 'fnb_manager'] }, 'pending')).toBe(true);
    expect(canUpdateMobileOrderStatus({ role: 'staff' }, 'pending')).toBe(false);
  });

  it('keeps kitchen and service transitions separated', () => {
    expect(canUpdateMobileOrderStatus({ role: 'kitchen_staff' }, 'pending')).toBe(true);
    expect(canUpdateMobileOrderStatus({ role: 'kitchen_staff' }, 'preparing')).toBe(true);
    expect(canUpdateMobileOrderStatus({ role: 'kitchen_staff' }, 'ready')).toBe(false);
    expect(canUpdateMobileOrderStatus({ role: 'service' }, 'ready')).toBe(true);
    expect(canUpdateMobileOrderStatus({ role: 'service' }, 'preparing')).toBe(false);
  });
});
