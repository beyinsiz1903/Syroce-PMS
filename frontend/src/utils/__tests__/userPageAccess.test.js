import { describe, it, expect } from 'vitest';
import { canAccessPath, canAccessNavItem, canAccessPmsTab, effectiveModuleScopes } from '../moduleAccess';
import catalog from '@/config/userAccessCatalog.json';

const reception = { role: 'front_desk', module_scopes: null, effective_permissions: ['view_bookings', 'view_folio', 'run_night_audit'] };

describe('user-specific page access', () => {
  it('keeps null module scopes compatible with role defaults, while [] denies', () => {
    expect(effectiveModuleScopes(reception)).toContain('frontdesk');
    expect(canAccessPath(reception, '/app/reservation-calendar')).toBe(true);
    expect(canAccessPath({ ...reception, module_scopes: [] }, '/app/reservation-calendar')).toBe(false);
  });
  it('applies page denial to aliases, menu links and PMS tabs', () => {
    const user = { ...reception, page_access: { rooms: false, calendar: false } };
    expect(canAccessPmsTab(user, 'rooms')).toBe(false);
    expect(canAccessPath(user, '/app/pms#rooms')).toBe(false);
    expect(canAccessPath(user, '/pms?tab=rooms')).toBe(false);
    expect(canAccessNavItem(user, { path: '/app/reservation-calendar', key: 'reservation_calendar' })).toBe(false);
    expect(canAccessPmsTab(user, 'bookings')).toBe(true);
  });
  it('keeps hotel administration and unclassified pages closed to staff', () => {
    for (const path of ['/app/settings', '/admin/otel-kullanicilari', '/app/ai']) {
      expect(canAccessPath(reception, path)).toBe(false);
    }
    expect(canAccessNavItem(reception, { path: '/app/dashboard', requireSuperAdmin: true })).toBe(false);
    expect(canAccessPath({ role: 'admin' }, '/admin/otel-kullanicilari')).toBe(true);
  });
  it('does not confuse scope, page and operation grants', () => {
    const staff = { role: 'staff', module_scopes: ['reports'], effective_permissions: [] };
    expect(canAccessPath(staff, '/reports')).toBe(false);
    const granted = { ...staff, effective_permissions: ['view_reports'] };
    expect(canAccessPath(granted, '/reports')).toBe(true);
    expect(canAccessPath({ ...granted, page_access: { reports: false } }, '/reports')).toBe(false);
    expect(canAccessPath(granted, '/app/general-ledger')).toBe(false);
  });
  it('opens night audit and cashier to reception without opening accounting', () => {
    expect(canAccessPath(reception, '/night-audit')).toBe(true);
    expect(canAccessPath(reception, '/app/cashier')).toBe(true);
    expect(canAccessPath(reception, '/app/general-ledger')).toBe(false);
  });
  it('protects every registered page and alias for a user with no scopes', () => {
    for (const page of catalog.pages) {
      for (const path of page.paths) expect(canAccessPath({ role: 'staff', module_scopes: [] }, path), path).toBe(false);
    }
  });
});
