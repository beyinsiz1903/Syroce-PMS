import { describe, expect, it } from 'vitest';

import { getRouteConfigs } from '../routeDefinitions';

const routeRuntime = {
  user: { role: 'super_admin', module_scopes: [] },
  tenant: {},
  modules: {},
  isAuthenticated: true,
  onLogout: () => {},
  hasFeature: () => true,
};

describe('route scope coverage', () => {
  it('does not allow protected routes to fall back to the legacy unscoped surface', () => {
    const unscoped = getRouteConfigs(routeRuntime)
      .filter((route) => !['public', 'redirect'].includes(route.type))
      .filter((route) => !Array.isArray(route.moduleScopes) || route.moduleScopes.some((scope) => String(scope).includes('legacy_unscoped')))
      .map((route) => route.path || route.to)
      .sort();

    expect(unscoped).toEqual([]);
  });
});
