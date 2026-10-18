import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { PRODUCT_MODULES, missingSetup, moduleCounts, moduleIntegrationLabel, moduleSetupLabel, moduleUsageLabel, moduleWorkspaceLabel, resolveModuleState } from '../moduleCatalog';

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

describe('agency extranet module state', () => {
  const agency = PRODUCT_MODULES.find((item) => item.key === 'agency_extranet');

  it('follows the channel manager until set explicitly, like the server', () => {
    expect(agency.path).toBe('/app/incoming-agency-contracts');
    expect(resolveModuleState(agency, { subscription_tier: 'enterprise', modules: { channel_manager: false } }).enabled).toBe(false);
    expect(resolveModuleState(agency, { subscription_tier: 'mini', modules: { channel_manager: true } }).enabled).toBe(true);
    expect(resolveModuleState(agency, { subscription_tier: 'enterprise', modules: { channel_manager: true, agency_extranet: false } }).enabled).toBe(false);
    expect(resolveModuleState(agency, { subscription_tier: 'mini', modules: { channel_manager: false, agency_extranet: true } }).enabled).toBe(true);
  });
});

describe('module readiness labels (server evidence)', () => {
  const spa = PRODUCT_MODULES.find((item) => item.key === 'spa');
  const cm = PRODUCT_MODULES.find((item) => item.key === 'channel_manager');
  const on = { enabled: true, path: '/x' };

  it('shows what the server found instead of a fixed placeholder', () => {
    const incomplete = { status: 'incomplete', setup: [{ key: 'spa_rooms', label: 'SPA odası', ok: true }, { key: 'spa_therapists', label: 'Terapist', ok: false }], usage: [] };
    expect(moduleSetupLabel(spa, on, incomplete)).toBe('Kurulum eksik (1)');
    expect(missingSetup(incomplete).map((row) => row.label)).toEqual(['Terapist']);
    expect(moduleSetupLabel(spa, on, { status: 'active', setup: [], usage: [] })).toBe('Kuruldu · kullanımda');
    expect(moduleSetupLabel(spa, on, { status: 'idle', setup: [], usage: [] })).toBe('Kuruldu · son dönemde kullanılmıyor');
    expect(moduleSetupLabel(spa, on, { status: 'ready', view: true })).toBe('Kurulum gerektirmiyor');
    expect(moduleUsageLabel(spa, {}, { usage: [{ label: 'Son 30 günde randevu', ok: false }] })).toBe('Son 30 günde randevu: yok');
    expect(moduleIntegrationLabel(cm, on, { setup: [{ ok: true }, { ok: false }] })).toBe('Bağlantı / ayar eksik');
    expect(moduleIntegrationLabel(cm, on, { setup: [{ ok: true }] })).toBe('Bağlantı kurulu');
  });

  it('has a server readiness rule for every product module', () => {
    const source = readFileSync(resolve(process.cwd(), '../backend/core/module_readiness.py'), 'utf8');
    const rules = new Set([...source.matchAll(/^ {4}"([a-z_]+)": \{/gm)].map((match) => match[1]));
    expect(PRODUCT_MODULES.map((item) => item.key).filter((key) => !rules.has(key))).toEqual([]);
  });
});
