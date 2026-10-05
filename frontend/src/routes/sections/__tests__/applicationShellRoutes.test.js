import { describe, expect, it } from 'vitest';

import { executiveOpsRoutes } from '../executiveOps';
import { mobileRoutes } from '../mobile';

const helpers = {
  p: (component) => ({ component }),
  pm: (component, moduleKey) => ({ component, moduleKey }),
};

describe('application shell routes', () => {
  it.each([
    ['/executive', executiveOpsRoutes, 'gm_dashboards'],
    ['/mobile/gm', mobileRoutes, 'pms_mobile'],
  ])('keeps the global application header on %s', (path, factory, layoutModule) => {
    const route = factory(helpers).find((item) => item.path === path);

    expect(route).toMatchObject({ wrapLayout: true, layoutModule });
  });
});
