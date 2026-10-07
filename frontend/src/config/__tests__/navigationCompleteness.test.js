import { describe, expect, it } from 'vitest';

import { NAV_GROUPS, NAV_GROUP_SECTIONS, NAV_ITEMS } from '@/config/navItems';
import { getRouteConfigs } from '@/routes/routeDefinitions';
import { orderedNavigationGroups } from '@/components/Layout';
import { PRODUCT_MODULES } from '@/lib/moduleCatalog';
import en from '@/locales/en.json';
import tr from '@/locales/tr.json';

const routePath = (value = '') => value.split('?')[0].split('#')[0];

describe('complete module navigation', () => {
  it('keeps every visible navigation target connected to a real application route', () => {
    const routes = getRouteConfigs({
      user: { role: 'super_admin' },
      tenant: {},
      modules: {},
      isAuthenticated: true,
      onLogout: () => {},
      hasFeature: () => true,
    });
    const registeredPaths = new Set(routes.map(({ path, to }) => routePath(path || to)));
    const missing = NAV_ITEMS
      .filter(({ hidden, path }) => !hidden && path)
      .filter(({ path }) => !registeredPaths.has(routePath(path)))
      .map(({ key, path }) => ({ key, path }));

    expect(missing).toEqual([]);
  });

  it('orders all available work groups without dropping secondary modules', () => {
    const ordered = orderedNavigationGroups(NAV_GROUPS, { role: 'front_desk' });
    expect(ordered).toHaveLength(NAV_GROUPS.length);
    expect(new Set(ordered.map(({ id }) => id))).toEqual(new Set(NAV_GROUPS.map(({ id }) => id)));
    expect(ordered.slice(0, 3).map(({ id }) => id)).toEqual(['frontdesk', 'guest', 'operations']);
  });

  it('gives every licensed product module a launch destination', () => {
    expect(PRODUCT_MODULES.filter(({ path }) => !path).map(({ key }) => key)).toEqual([]);
  });

  it('keeps every visible navigation label translated in English and Turkish', () => {
    const visibleKeys = [...new Set(NAV_ITEMS.filter(({ hidden }) => !hidden).map(({ key }) => key))];
    expect(visibleKeys.filter((key) => !en.navKeys?.[key])).toEqual([]);
    expect(visibleKeys.filter((key) => !tr.navKeys?.[key])).toEqual([]);

    Object.entries(NAV_GROUP_SECTIONS).forEach(([groupId, sections]) => {
      sections.forEach(({ id }) => {
        expect(en.navSections?.[groupId]?.[id], `missing English section ${groupId}.${id}`).toBeTruthy();
        expect(tr.navSections?.[groupId]?.[id], `missing Turkish section ${groupId}.${id}`).toBeTruthy();
      });
    });
  });
});
