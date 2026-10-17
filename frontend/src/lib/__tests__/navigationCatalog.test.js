import { describe, expect, it } from 'vitest';

import { accessibleNavigationItems } from '@/lib/navigationCatalog';

const admin = {
  role: 'admin',
  module_scopes: [
    'frontdesk', 'cashier', 'finance', 'reports', 'sales', 'channel_manager',
    'night_audit',
  ],
};

describe('accessibleNavigationItems compact workspace', () => {
  it('fails closed to the Sapanca-Kartepe allow-list and applies its labels', () => {
    const items = accessibleNavigationItems({
      user: admin,
      tenant: {
        visible_nav_items: [
          'dashboard', 'reservation_calendar', 'pms', 'cashier_workspace',
          'unified_rate_manager', 'settings',
        ],
        nav_item_labels: { settings: 'Yönetim' },
      },
      hasModule: () => true,
    });

    expect(items.map(({ key }) => key)).toEqual([
      'dashboard', 'reservation_calendar', 'pms', 'unified_rate_manager',
      'settings', 'cashier_workspace',
    ]);
    expect(items.find(({ key }) => key === 'settings')?.label).toBe('Yönetim');
    expect(items.some(({ key }) => key === 'room_mapping_wizard')).toBe(false);
  });

  it('keeps the legacy catalogue behavior when no allow-list is configured', () => {
    const items = accessibleNavigationItems({
      user: admin,
      tenant: {},
      hasModule: () => true,
    });

    expect(items.some(({ key }) => key === 'dashboard')).toBe(true);
    expect(items.some(({ key }) => key === 'room_mapping_wizard')).toBe(true);
  });
});

describe('Agency Extranet is licensed apart from the OTA channel manager', () => {
  const keysFor = modules => accessibleNavigationItems({ user: admin, tenant: {}, hasModule: key => modules.includes(key) })
    .map(({ key }) => key);

  it('an agency-only hotel sees the agency pages and shares rates, not the OTA pages', () => {
    const keys = keysFor(['agency_extranet']);
    expect(keys).toEqual(expect.arrayContaining(['incoming_agency_contracts', 'agency_statements', 'unified_rate_manager']));
    expect(keys).not.toContain('channel_connections');
  });

  it('an OTA-only hotel keeps the rate manager but not the agency pages', () => {
    const keys = keysFor(['channel_manager']);
    expect(keys).toContain('unified_rate_manager');
    expect(keys).not.toContain('incoming_agency_contracts');
  });
});
