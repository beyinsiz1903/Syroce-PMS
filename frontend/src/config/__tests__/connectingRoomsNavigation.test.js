import { describe, expect, it } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';

describe('connecting rooms navigation', () => {
  it('exposes connecting-room management to hotel managers under Operations', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'connecting_rooms');

    expect(item).toMatchObject({
      label: 'Bağlantılı Odalar',
      path: '/suite-connecting',
      moduleKey: 'pms',
      navGroup: 'operations',
      allowedRoles: ['admin', 'supervisor', 'super_admin'],
    });
  });
});
