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
  it('classifies migration without relaxing its PMS entitlement or administrator gates', () => {
    const migration = getRouteConfigs(routeRuntime).find((route) => route.path === '/app/data-migration');

    expect(migration).toMatchObject({
      type: 'module',
      moduleKey: 'pms',
      moduleScopes: ['frontdesk'],
      strict: true,
      allowedRoles: ['admin', 'super_admin'],
    });
    expect(migration.skipModuleScopeBoundary).not.toBe(true);
  });

  it('gives agency recovery screens the same scope as agency administration', () => {
    const routes = getRouteConfigs(routeRuntime);
    const agencies = routes.find((route) => route.path === '/admin/agencies');
    const repairs = routes.find((route) => route.path === '/admin/agency-integrations');
    const salesLocks = routes.find((route) => route.path === '/admin/agency-sales-locks');
    expect(repairs.moduleScopes).toEqual(agencies.moduleScopes);
    expect(repairs.type).toEqual(agencies.type);
    expect(salesLocks.moduleScopes).toEqual(agencies.moduleScopes);
    expect(salesLocks.type).toEqual(agencies.type);
  });

  it('does not allow protected routes to fall back to the legacy unscoped surface', () => {
    const unscoped = getRouteConfigs(routeRuntime)
      .filter((route) => !['public', 'redirect'].includes(route.type))
      .filter((route) => !Array.isArray(route.moduleScopes) || route.moduleScopes.some((scope) => String(scope).includes('legacy_unscoped')))
      .map((route) => route.path || route.to)
      .sort();

    expect(unscoped).toEqual([]);
  });
});
