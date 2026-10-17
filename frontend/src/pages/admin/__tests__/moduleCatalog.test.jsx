import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { NAV_ITEMS } from '@/config/navItems';
import { MODULE_GROUPS, isModuleIncludedInPlan } from '../tenantConstants';
import { setPlanCatalogForTests } from '@/lib/planCatalog';

const items = MODULE_GROUPS.flatMap(group => group.items);
const keys = new Set(items.map(item => item.key));

describe('tenant module catalogue parity', () => {
  it('has unique entries and covers every tenant-facing menu module', () => {
    expect(keys.size).toBe(items.length);
    const missing = NAV_ITEMS.filter(item => item.moduleKey && !item.requireSuperAdmin && !keys.has(item.moduleKey));
    expect(missing).toEqual([]);
  });

  it('keeps platform administration out of hotel module switches', () => {
    expect(keys.has('admin_panel')).toBe(false);
    const platform = NAV_ITEMS.filter(item => item.moduleKey === 'admin_panel');
    expect(platform.length).toBeGreaterThan(0);
    expect(platform.every(item => item.requireSuperAdmin)).toBe(true);
  });

  it('covers all backend entitlement modules and plan flags', () => {
    const registry = readFileSync(resolve(process.cwd(), '../backend/core/entitlements/registry.py'), 'utf8');
    const plan = readFileSync(resolve(process.cwd(), '../backend/domains/admin/subscription_models.py'), 'utf8');
    const backendKeys = [
      ...[...registry.matchAll(/^ {4}"([a-z_]+)": ModuleDefinition/gm)].map(match => match[1]),
      ...[...plan.matchAll(/"([a-z_]+)": (?:True|False)/g)].map(match => match[1]),
    ];
    expect(backendKeys.length).toBeGreaterThan(20);
    expect([...new Set(backendKeys)].filter(key => !keys.has(key))).toEqual([]);
  });

  it('never silently grants the newly exposed optional modules in any plan', () => {
    for (const key of ['hr', 'pos_fnb', 'parking']) {
      for (const tier of ['mini', 'basic', 'professional', 'enterprise']) {
        expect(isModuleIncludedInPlan(items.find(item => item.key === key), tier)).toBe(false);
      }
    }
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'quick_id'), 'enterprise')).toBe(false);
  });

  it('decides plan scope from the server catalogue only, never by itself', () => {
    setPlanCatalogForTests(null);
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'pms'), 'enterprise')).toBe(false);
    setPlanCatalogForTests({ professional: { pms: true }, enterprise: { pms: true, ai: true } });
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'pms'), 'pro')).toBe(true); // legacy alias
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'ai'), 'enterprise')).toBe(true);
    // A paid add-on stays paid even if a catalogue were to grant it.
    setPlanCatalogForTests({ enterprise: { ai_chatbot: true, quick_id: true } });
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'ai_chatbot'), 'enterprise')).toBe(false);
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'quick_id'), 'enterprise')).toBe(false);
  });

  it('keeps platform screens out of the hotel product catalogue', () => {
    for (const key of ['system_health', 'security_hardening', 'encryption_management', 'runtime_cockpit', 'operator_incident', 'control_plane', 'lockdown', 'data_model']) {
      expect(keys.has(key)).toBe(false);
    }
  });

  it('keeps legacy PMS Lite narrower than the later Mini commercial tier', () => {
    // Excerpt of the server's defaults_by_tier.pms_lite.
    setPlanCatalogForTests({ pms_lite: { pms: true, invoices_basic: false, channel_manager_lite: false } });
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'pms'), 'pms_lite')).toBe(true);
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'invoices_basic'), 'pms_lite')).toBe(false);
    expect(isModuleIncludedInPlan(items.find(item => item.key === 'channel_manager_lite'), 'pms_lite')).toBe(false);
  });
});
