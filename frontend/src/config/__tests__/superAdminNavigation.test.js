import { describe, expect, it } from 'vitest';

import { NAV_GROUP_SECTIONS, NAV_ITEMS } from '@/config/navItems';
import { sectionNavItems } from '@/components/Layout';

const visibleItemsFor = (group) => NAV_ITEMS.filter((item) => item.navGroup === group && !item.hidden);

describe('professional super admin navigation', () => {
  it('keeps hotel-facing channel tools separate from super admin operations', () => {
    const systemItems = visibleItemsFor('system');
    const adminItems = visibleItemsFor('admin');

    expect(systemItems.some((item) => item.requireSuperAdmin)).toBe(false);
    expect(systemItems.map((item) => item.key)).toEqual(expect.arrayContaining([
      'channels_hub',
      'integration_hub',
      'unified_rate_manager',
      'room_mapping_wizard',
    ]));
    expect(adminItems.map((item) => item.key)).toEqual(expect.arrayContaining([
      'admin_hub',
      'admin_control_panel',
      'integrations_overview',
      'channel_ops',
      'integration_credentials',
    ]));
  });

  it('places every visible system and admin link under a named section', () => {
    for (const group of ['system', 'admin']) {
      const allowedSections = new Set(NAV_GROUP_SECTIONS[group].map(({ id }) => id));
      for (const item of visibleItemsFor(group)) {
        expect(allowedSections.has(item.navSection), `${item.key} has an unknown section`).toBe(true);
      }

      const sections = sectionNavItems(group, visibleItemsFor(group));
      expect(sections.every((section) => section.label && section.items.length > 0)).toBe(true);
      expect(sections.flatMap((section) => section.items)).toHaveLength(visibleItemsFor(group).length);
    }
  });
});
