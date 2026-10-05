import { describe, expect, it } from 'vitest';

import { NAV_ITEMS } from '@/config/navItems';
import { financeReportsRoutes } from '@/routes/sections/financeReports';

describe('pending accounts receivable navigation', () => {
  it('provides a finance menu entry for the existing protected screen', () => {
    expect(NAV_ITEMS.find(({ key }) => key === 'pending_ar')).toMatchObject({
      label: 'Bekleyen Alacaklar',
      path: '/pending-ar',
      moduleKey: 'invoices',
      navGroup: 'backoffice',
    });

    const route = financeReportsRoutes({ p: (component) => ({ component, type: 'protected' }) })
      .find(({ path }) => path === '/pending-ar');
    expect(route).toMatchObject({ path: '/pending-ar', type: 'protected', layoutModule: 'pending-ar' });
  });
});
