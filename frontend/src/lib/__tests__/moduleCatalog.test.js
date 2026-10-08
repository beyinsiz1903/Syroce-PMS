import { describe, expect, it } from 'vitest';
import { PRODUCT_MODULES, moduleCounts, moduleIntegrationLabel, moduleSetupLabel, moduleUsageLabel, moduleWorkspaceLabel, resolveModuleState } from '../moduleCatalog';

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

  it('routes the module marketplace entitlement to the module store, not supplies sales', () => {
    const marketplace = PRODUCT_MODULES.find((item) => item.key === 'marketplace');

    expect(marketplace.label).toBe('Modül Mağazası');
    expect(marketplace.path).toBe('/app/module-store');
    expect(marketplace.path).not.toBe('/app/marketplace');
  });

  it('reports enabled modules without inventing launch routes', () => {
    const counts = moduleCounts({ subscription_tier: 'mini', modules: { pms: true } });
    expect(counts.total).toBe(PRODUCT_MODULES.length);
    expect(counts.enabled).toBeGreaterThan(0);
    expect(counts.launchable).toBeLessThanOrEqual(counts.enabled);
    expect(counts.needsSetup).toBe(counts.enabled - counts.launchable);
  });
});

describe('module operational evidence', () => {
  it('does not claim an integration is healthy without evidence', () => {
    const item = PRODUCT_MODULES.find((module) => module.key === 'channel_manager');
    expect(moduleIntegrationLabel(item, { enabled: true })).toBe('Sağlık verisi bekleniyor');
    expect(moduleIntegrationLabel(item, { enabled: false })).toBe('Erişim kapalı');
  });

  it('summarizes only mapped usage events', () => {
    const item = PRODUCT_MODULES.find((module) => module.key === 'reports');
    expect(moduleUsageLabel(item, { period_days: 30, events: { report_generated: 7 } })).toBe('Son 30 günde 7 işlem');
  });

  it('does not confuse a workspace route with completed tenant setup', () => {
    const item = PRODUCT_MODULES.find((module) => module.key === 'folio_management');
    const state = resolveModuleState(item, { subscription_tier: 'enterprise', modules: { folio_management: true } });
    expect(moduleWorkspaceLabel(item, state)).toBe('Çalışma alanı bağlı');
    expect(moduleSetupLabel(item, state)).toBe('Kurulum kanıtı yok');
  });
});
