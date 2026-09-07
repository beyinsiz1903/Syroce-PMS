import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { NAV_ITEMS } from '@/config/navItems';
import { MODULE_GROUPS, isModuleIncludedInPlan } from '../tenantConstants';

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
});
