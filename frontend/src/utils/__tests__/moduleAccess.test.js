import { describe, expect, it } from 'vitest';

import {
  effectiveModuleScopes,
  hasAnyModuleAccess,
  hasModuleAccess,
  moduleScopesForNavItem,
  moduleScopesForPath,
  moduleScopesForPmsTab,
  supplementalModuleNavItems,
} from '../moduleAccess';

describe('moduleAccess', () => {
  it('treats explicit module_scopes as authoritative', () => {
    const user = { role: 'admin', module_scopes: ['cashier'] };
    expect(effectiveModuleScopes(user)).toEqual(['cashier']);
    expect(hasModuleAccess(user, 'cashier')).toBe(true);
    expect(hasModuleAccess(user, 'finance')).toBe(false);
  });

  it('fails closed for malformed explicit scopes', () => {
    expect(effectiveModuleScopes({ role: 'admin', module_scopes: 'cashier' })).toEqual([]);
    expect(hasModuleAccess({ role: 'staff', module_scopes: ['made-up'] }, 'cashier')).toBe(false);
  });

  it('preserves super-admin wildcard access', () => {
    const user = { role: 'super_admin', module_scopes: [] };
    expect(hasModuleAccess(user, 'channel_manager')).toBe(true);
    expect(hasAnyModuleAccess(user, ['cashier', 'reports'])).toBe(true);
  });

  it('maps protected routes to the expected user module scope', () => {
    expect(moduleScopesForPath('/app/procurement')).toEqual(['procurement']);
    expect(moduleScopesForPath('/maintenance/work-orders')).toEqual(['maintenance']);
    expect(moduleScopesForPath('/app/cashier')).toEqual(['cashier']);
    expect(moduleScopesForPath('/app/tasks')).toEqual(['tasks']);
    expect(moduleScopesForPath('/app/dashboard')).toEqual([]);
  });

  it('maps navigation items and PMS tabs to user scopes', () => {
    expect(moduleScopesForNavItem({ key: 'invoices', path: '/app/invoices' })).toEqual(['invoice']);
    expect(moduleScopesForPmsTab('housekeeping')).toEqual(['housekeeping']);
    expect(moduleScopesForPmsTab('cashier')).toEqual(['cashier']);
    expect(moduleScopesForPmsTab('unknown-tab')).toEqual(['frontdesk']);
  });

  it('only supplies module workspaces granted to the user', () => {
    const user = { role: 'staff', module_scopes: ['tasks'] };
    const items = supplementalModuleNavItems(user);
    expect(items.map((item) => item.key)).toEqual(['tasks_workspace']);
  });
});
