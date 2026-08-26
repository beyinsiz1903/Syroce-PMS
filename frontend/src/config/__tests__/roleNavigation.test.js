import { describe, expect, it } from 'vitest';

import { primaryNavigationGroupIds } from '@/components/Layout';

describe('role-aware primary navigation', () => {
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
