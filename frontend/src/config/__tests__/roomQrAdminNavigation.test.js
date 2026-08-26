import { describe, expect, it, vi } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';
import { securityAdminRoutes } from '@/routes/sections/securityAdmin';

describe('room QR admin access', () => {
  it('shows the QR code screen to hotel admins without exposing it to staff roles', () => {
    const item = NAV_ITEMS.find(({ key }) => key === 'room_qr_codes');

    expect(item).toMatchObject({
      path: '/admin/room-qr-codes',
      moduleKey: 'room_qr_requests',
      navGroup: 'admin',
      navSection: 'properties',
      allowedRoles: ['admin', 'super_admin'],
    });
    expect(item.requireSuperAdmin).not.toBe(true);
  });

  it('uses the normal authenticated route instead of the superadmin-only guard', () => {
    const p = vi.fn((component) => ({ type: 'protected', component }));
    const pa = vi.fn((component) => ({
      type: 'protected',
      component,
      requireSuperAdmin: true,
    }));
    const route = securityAdminRoutes({ p, pa })
      .find(({ path }) => path === '/admin/room-qr-codes');

    expect(route.type).toBe('protected');
    expect(route.requireSuperAdmin).not.toBe(true);
    expect(p).toHaveBeenCalledWith(route.component);
  });
});
