import { describe, expect, it } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';
import { coreOperationsRoutes } from '@/routes/sections/coreOperations';

describe('unified CRM navigation', () => {
  it('exposes one canonical CRM entry and hides the legacy complaint entry', () => {
    const crm = NAV_ITEMS.find((item) => item.key === 'guest_journey');
    const complaints = NAV_ITEMS.find((item) => item.key === 'service_recovery');

    expect(crm).toMatchObject({ label: 'CRM Merkezi', path: '/crm', navGroup: 'guest' });
    expect(complaints.hidden).toBe(true);
  });

  it('keeps old guest journey bookmarks working through the CRM journey tab', () => {
    const routes = coreOperationsRoutes({
      p: (component) => ({ component }), pa: (component) => ({ component }),
      pm: (component) => ({ component }), modules: {},
    });
    expect(routes.find((route) => route.path === '/guest-journey')).toMatchObject({
      type: 'redirect',
      to: '/crm?tab=journeys',
    });
  });
});
