import { describe, expect, it } from 'vitest';

import { hasModuleScope } from '../authRoles';


describe('hasModuleScope', () => {
  it('preserves legacy access when module_scopes is absent or empty', () => {
    expect(hasModuleScope({ role: 'staff' }, 'pms')).toBe(true);
    expect(hasModuleScope({ role: 'staff', module_scopes: [] }, 'reports')).toBe(true);
  });

  it('treats a non-empty scope list as a restrictive allowlist', () => {
    const user = { role: 'staff', module_scopes: ['pms', 'reservation-calendar'] };

    expect(hasModuleScope(user, 'pms')).toBe(true);
    expect(hasModuleScope(user, 'reservation_calendar')).toBe(true);
    expect(hasModuleScope(user, 'invoices')).toBe(false);
  });

  it('supports global and prefix wildcards', () => {
    expect(hasModuleScope({ role: 'staff', module_scopes: ['*'] }, 'pos')).toBe(true);
    expect(
      hasModuleScope({ role: 'staff', module_scopes: ['finance.*'] }, 'finance_reports'),
    ).toBe(true);
    expect(
      hasModuleScope({ role: 'staff', module_scopes: ['finance.*'] }, 'finance.general_ledger'),
    ).toBe(true);
  });

  it('always allows the protected super-admin account', () => {
    expect(
      hasModuleScope(
        { role: 'super_admin', module_scopes: ['reports'] },
        'maintenance',
      ),
    ).toBe(true);
  });
});
