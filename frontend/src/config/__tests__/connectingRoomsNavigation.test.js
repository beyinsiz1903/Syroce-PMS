import { describe, expect, it } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';

describe('connecting rooms navigation', () => {
  it('keeps connection setup out of daily navigation and available from settings', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'connecting_rooms');

    expect(item).toMatchObject({
      label: 'Bağlantılı Oda Tanımları',
      path: '/suite-connecting',
      moduleKey: 'pms',
      group: 'settings',
      hidden: true,
      allowedRoles: ['admin', 'supervisor', 'super_admin'],
    });
  });
});
