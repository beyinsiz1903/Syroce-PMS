import { describe, expect, it } from 'vitest';

import { desktopQuickNavigationItems, primaryNavigationGroupIds } from '@/components/Layout';

describe('role-aware primary navigation', () => {
  it('keeps PMS and calendar visible as direct desktop shortcuts', () => {
    const visible = [
      { key: 'reservation_calendar', path: '/app/reservation-calendar' },
      { key: 'reports', path: '/reports' },
      { key: 'pms', path: '/app/pms' },
    ];

    expect(desktopQuickNavigationItems(visible).map((item) => item.key)).toEqual([
      'pms',
      'reservation_calendar',
    ]);
  });

  it('keeps reception focused on the three operational areas', () => {
    expect(primaryNavigationGroupIds({ role: 'front_desk' })).toEqual([
      'frontdesk', 'guest', 'operations',
    ]);
  });

  it('gives finance and GM roles dedicated work areas', () => {
    expect(primaryNavigationGroupIds({ role: 'accounting' })).toEqual([
      'backoffice', 'reports', 'sales',
    ]);
    expect(primaryNavigationGroupIds({ role: 'gm' })).toEqual([
      'sales', 'operations', 'reports',
    ]);
  });

  it('keeps platform tools first for superadmins', () => {
    expect(primaryNavigationGroupIds({ role: 'super_admin' }, true)).toEqual([
      'admin', 'system', 'reports',
    ]);
  });
});
