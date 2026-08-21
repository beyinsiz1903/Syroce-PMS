import { describe, expect, it } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';
import { moduleScopesForNavItem, moduleScopesForPath } from '@/utils/moduleAccess';

describe('hotel admin integration center navigation', () => {
  it('exposes one integration center entry to hotel users', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'integration_hub');

    expect(item).toMatchObject({
      label: 'Entegrasyon Merkezi',
      path: '/app/integration-hub',
      navGroup: 'system',
    });
    expect(item.hidden).not.toBe(true);
    expect(item.requireSuperAdmin).not.toBe(true);
    expect(moduleScopesForNavItem(item)).toEqual(['channel_manager', 'invoice']);
    expect(moduleScopesForPath(item.path)).toEqual(['channel_manager', 'invoice']);
  });

  it('hides duplicate channel menu entries while retaining their routes', () => {
    const duplicateKeys = [
      'cm_dashboard',
      'go_live_readiness',
      'channel_manager',
      'channel_connections',
    ];

    for (const key of duplicateKeys) {
      expect(NAV_ITEMS.find((item) => item.key === key)?.hidden).toBe(true);
    }
  });
});
