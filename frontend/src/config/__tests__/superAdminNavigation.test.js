import { describe, expect, it } from 'vitest';

import { NAV_GROUP_SECTIONS, NAV_ITEMS } from '@/config/navItems';
import { sectionNavItems } from '@/components/Layout';

const visibleItemsFor = (group) => NAV_ITEMS.filter((item) => item.navGroup === group && !item.hidden);

describe('professional super admin navigation', () => {
  it('exposes Transfer & Otopark in the frontdesk guest services menu', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'transfer_parking');

    expect(item).toMatchObject({
      label: 'Transfer & Otopark',
      path: '/transfer-parking',
      moduleKey: 'parking',
      navGroup: 'frontdesk',
      navSection: 'guest_services',
    });
    expect(item.hidden).not.toBe(true);
  });

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

  it('exposes the system health dashboard from super admin platform operations', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'observability');

    expect(item).toMatchObject({
      label: 'Sistem Sağlığı',
      path: '/observability',
      navGroup: 'admin',
      navSection: 'platform',
      requireSuperAdmin: true,
    });
    expect(item.hidden).not.toBe(true);
  });

  it('exposes platform tools that were previously assigned to an undefined menu group', () => {
    const expected = {
      control_plane: 'platform',
      runtime_cockpit: 'platform',
      incident_panel: 'platform',
      encryption_management: 'platform',
      production_golive: 'platform',
      integration_observability: 'platform',
      data_model: 'platform',
      infra_hardening: 'platform',
      hrv2_ops: 'integrations',
    };

    for (const [key, navSection] of Object.entries(expected)) {
      expect(NAV_ITEMS.find((candidate) => candidate.key === key)).toMatchObject({
        navGroup: 'admin',
        navSection,
        requireSuperAdmin: true,
      });
    }
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
