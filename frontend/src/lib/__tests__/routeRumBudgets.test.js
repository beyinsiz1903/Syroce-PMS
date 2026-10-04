import { describe, expect, it } from 'vitest';
import { RUM_ROUTE_BUDGETS, RUM_ROUTE_PATHS, isRumRoute } from '@/lib/routeRumBudgets';

describe('module-entry RUM budgets', () => {
  it('covers the recurrent entry route for every primary operational workspace', () => {
    expect(RUM_ROUTE_PATHS).toHaveLength(28);
    expect(RUM_ROUTE_PATHS).toEqual(expect.arrayContaining([
      '/app/dashboard', '/app/pms', '/app/reservation-calendar',
      '/night-audit', '/housekeeping', '/pos', '/app/cashier',
      '/app/invoices', '/app/raporlar', '/app/rms', '/sales',
      '/app/channel-manager', '/channels', '/app/integration-hub', '/hr',
    ]));
  });

  it('uses finite user-perceived budgets and never tracks non-entry paths', () => {
    for (const [path, budget] of Object.entries(RUM_ROUTE_BUDGETS)) {
      expect(isRumRoute(path)).toBe(true);
      expect(budget.module).toMatch(/^[a-z-]+$/);
      expect(budget.routeMs).toBeGreaterThan(0);
      expect(budget.lcpMs).toBeGreaterThan(0);
      expect(budget.inpMs).toBeGreaterThan(0);
      expect(budget.apiP95Ms).toBeGreaterThan(0);
    }
    expect(isRumRoute('/folio-detail/secret')).toBe(false);
  });
});
