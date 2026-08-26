import { describe, expect, it } from 'vitest';

import { sectionNavItems } from '@/components/Layout';
import { NAV_GROUP_SECTIONS, NAV_ITEMS } from '@/config/navItems';
import { SUPPLEMENTAL_MODULE_NAV_ITEMS } from '@/utils/moduleAccess';

const item = (key) => NAV_ITEMS.find((candidate) => candidate.key === key);

describe('workflow-oriented hotel navigation', () => {
  it('moves reception work out of the operations menu', () => {
    expect(item('wake_up_calls')).toMatchObject({
      navGroup: 'frontdesk',
      navSection: 'guest_services',
    });
    expect(item('connecting_rooms')).toMatchObject({
      navGroup: 'frontdesk',
      navSection: 'room_management',
    });
  });

  it('keeps operational work in named task sections', () => {
    expect(item('shift_handover').navSection).toBe('daily');
    expect(item('lost_found').navSection).toBe('guest_requests');
    expect(item('room_qr_requests').navSection).toBe('guest_requests');
    expect(item('operational_events').navSection).toBe('incidents');
    expect(SUPPLEMENTAL_MODULE_NAV_ITEMS.find(({ key }) => key === 'tasks_workspace'))
      .toMatchObject({ navGroup: 'operations', navSection: 'daily' });
  });

  it('places administrative tools in Administration instead of daily operations', () => {
    expect(item('security_hub')).toMatchObject({
      navGroup: 'admin',
      navSection: 'centers',
    });
    expect(item('room_qr_codes')).toMatchObject({
      navGroup: 'admin',
      navSection: 'properties',
    });
  });

  it('does not leave front-desk or operations links under an unnamed Other section', () => {
    for (const group of ['frontdesk', 'operations']) {
      const configuredItems = [
        ...NAV_ITEMS.filter((candidate) => candidate.navGroup === group && !candidate.hidden),
        ...SUPPLEMENTAL_MODULE_NAV_ITEMS.filter((candidate) => candidate.navGroup === group),
      ];
      const allowedSections = new Set(NAV_GROUP_SECTIONS[group].map(({ id }) => id));

      expect(configuredItems.every((candidate) => allowedSections.has(candidate.navSection))).toBe(true);
      expect(sectionNavItems(group, configuredItems).some(({ id }) => id === 'other')).toBe(false);
    }
  });
});
