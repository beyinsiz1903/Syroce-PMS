import { describe, expect, it } from 'vitest';

import { accessibleNavigationItems, explainNavigationItem, moduleNavigationStatus } from '@/lib/navigationCatalog';
import { NAV_ITEMS as NAV_ITEMS_FOR_TEST } from '@/config/navItems';

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

describe('explainNavigationItem: one menu decision with its reason', () => {
  const page = (key) => NAV_ITEMS_FOR_TEST.find((item) => item.key === key);
  const options = (extra = {}) => ({ user: admin, tenant: {}, hasModule: () => true, ...extra });

  it('says why a page is not in the menu, in rule order', () => {
    const statements = page('agency_statements');
    expect(explainNavigationItem(statements, options())).toEqual({ visible: true, reason: null, reasonLabel: null });
    expect(explainNavigationItem(statements, options({ tenant: { hidden_nav_items: ['agency_statements'] } })).reason).toBe('hidden_item');
    expect(explainNavigationItem(statements, options({ tenant: { visible_nav_items: ['dashboard'] } })).reason).toBe('not_in_property_list');
    expect(explainNavigationItem(statements, options({ tenant: { hidden_nav_groups: [statements.navGroup] } })).reason).toBe(statements.navGroup ? 'hidden_group' : null);
    const off = explainNavigationItem(statements, options({ hasModule: () => false, moduleOffReason: () => 'not_in_plan' }));
    expect(off).toMatchObject({ visible: false, reason: 'not_in_plan', reasonLabel: 'Pakette yok' });
    expect(explainNavigationItem(statements, options({ hasModule: () => false })).reason).toBe('module_off');
  });

  it('agrees with the menu for every page', () => {
    const tenant = { visible_nav_items: ['dashboard', 'agency_statements', 'settings'], hidden_nav_items: ['settings'] };
    const hasModule = (key) => key !== 'agency_extranet';
    const shown = new Set(accessibleNavigationItems({ user: admin, tenant, hasModule }).map(({ key }) => key));
    for (const item of NAV_ITEMS_FOR_TEST) {
      expect(explainNavigationItem(item, { user: admin, tenant, hasModule }).visible).toBe(shown.has(item.key));
    }
  });

  it('answers "enabled but not in the menu" per module (property allow-list)', () => {
    const pages = moduleNavigationStatus('agency_extranet', options({ tenant: { visible_nav_items: ['dashboard', 'incoming_agency_contracts'] } }));
    expect(pages.length).toBeGreaterThan(1);
    expect(pages.find((row) => row.key === 'incoming_agency_contracts').visible).toBe(true);
    expect(pages.find((row) => row.key === 'agency_statements')).toMatchObject({ visible: false, reason: 'not_in_property_list' });
    // Shared pages count for each module that opens them.
    expect(moduleNavigationStatus('agency_extranet', options()).some((row) => row.key === 'unified_rate_manager')).toBe(true);
  });
});
