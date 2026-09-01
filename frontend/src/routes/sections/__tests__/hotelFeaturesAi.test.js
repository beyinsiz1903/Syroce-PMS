import { describe, expect, it, vi } from 'vitest';

vi.mock('../lazyPages', () => ({
  OnlineCheckin: 'OnlineCheckin',
  FlashReport: 'FlashReport',
  GroupSales: 'GroupSales',
  SalesCRM: 'SalesCRM',
  ServiceRecovery: 'ServiceRecovery',
  SpaWellness: 'SpaWellness',
  SpaDiningPackages: 'SpaDiningPackages',
  MultiProperty: 'MultiProperty',
  StaffManagement: 'StaffManagement',
  StaffProfile: 'StaffProfile',
  ShiftPlannerPage: 'ShiftPlannerPage',
  HRHub: 'HRHub',
  FnBComplete: 'FnBComplete',
  FnbBeoGenerator: 'FnbBeoGenerator',
  KitchenDisplay: 'KitchenDisplay',
  AIChatbot: 'AIChatbot',
  DynamicPricing: 'DynamicPricing',
  AIWhatsAppConcierge: 'AIWhatsAppConcierge',
  PredictiveAnalytics: 'PredictiveAnalytics',
  SocialMediaRadar: 'SocialMediaRadar',
  RevenueAutopilot: 'RevenueAutopilot',
  RevenueAutopilotMonitor: 'RevenueAutopilotMonitor',
}));

import { getRequiredModule } from '@/components/PlanRouteGuard';
import { hotelFeaturesAiRoutes } from '../hotelFeaturesAi';

describe('multi-property navigation', () => {
  const helpers = {
    p: (component) => ({ component }),
    pm: (component, moduleKey) => ({ component, moduleKey }),
  };

  it('uses the plan-guarded app path as the canonical chain dashboard URL', () => {
    const routes = hotelFeaturesAiRoutes(helpers);
    const canonical = routes.find((route) => route.path === '/app/multi-property');
    const legacy = routes.find((route) => route.path === '/multi-property');

    expect(canonical.component).toBe('MultiProperty');
    expect(canonical).toMatchObject({
      wrapLayout: true,
      layoutModule: 'multi-property',
    });
    expect(getRequiredModule(canonical.path)).toBe('multi_property');
    expect(legacy).toMatchObject({
      type: 'redirect',
      to: '/app/multi-property',
    });
  });
});
