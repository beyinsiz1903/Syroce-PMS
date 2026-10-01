import { describe, expect, it } from 'vitest';
import { PRODUCT_MODULES, moduleCounts, resolveModuleState } from '../moduleCatalog';

describe('module catalog', () => {
  it('contains unique product keys and omits sub-navigation flags', () => {
    const keys = PRODUCT_MODULES.map((item) => item.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.some((key) => key.includes('.'))).toBe(false);
  });

  it('uses explicit tenant decisions before plan defaults', () => {
    const pms = PRODUCT_MODULES.find((item) => item.key === 'pms');
    expect(resolveModuleState(pms, { subscription_tier: 'enterprise', modules: { pms: false } }).enabled).toBe(false);
    expect(resolveModuleState(pms, { subscription_tier: 'mini', modules: { pms: true } }).enabled).toBe(true);
  });

  it('exposes the resolved workspace path with the module state', () => {
    const pms = PRODUCT_MODULES.find((item) => item.key === 'pms');
    const state = resolveModuleState(pms, { subscription_tier: 'mini', modules: { pms: true } });

    expect(state.path).toBe('/app/reservation-calendar');
    expect(state.launchable).toBe(true);
  });

  it('reports enabled modules without inventing launch routes', () => {
    const counts = moduleCounts({ subscription_tier: 'mini', modules: { pms: true } });
    expect(counts.total).toBe(PRODUCT_MODULES.length);
    expect(counts.enabled).toBeGreaterThan(0);
    expect(counts.launchable).toBeLessThanOrEqual(counts.enabled);
    expect(counts.needsSetup).toBe(counts.enabled - counts.launchable);
  });
});
