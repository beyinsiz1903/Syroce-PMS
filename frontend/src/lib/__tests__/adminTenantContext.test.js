import { beforeEach, describe, expect, it } from 'vitest';

import {
  ADMIN_TENANT_CONTEXT_KEY,
  isAdminTenantContextActive,
  persistEnteredTenantContext,
  persistExitedTenantContext,
  reconcileAdminTenantContext,
  restoreOriginTenantContext,
} from '@/lib/adminTenantContext';

const origin = {
  user: { id: 'super-1', tenant_id: 'tenant-origin', role: 'super_admin', is_impersonating: false },
  tenant: { id: 'tenant-origin', property_name: 'Platform Hotel' },
  modules: { pms: true },
};

const entered = {
  access_token: 'target-access-token',
  expires_at: 2_000_000_000,
  user: {
    id: 'super-1',
    tenant_id: 'tenant-target',
    role: 'super_admin',
    is_impersonating: true,
    actor_tenant_id: 'tenant-origin',
  },
  tenant: { id: 'tenant-target', property_name: 'Target Hotel' },
  modules: { channel_manager: true },
  origin,
};

describe('admin tenant context storage', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('persists target and origin snapshots atomically', () => {
    persistEnteredTenantContext(entered);

    expect(JSON.parse(localStorage.getItem('user'))).toMatchObject({
      tenant_id: 'tenant-target',
      is_impersonating: true,
    });
    expect(JSON.parse(localStorage.getItem('tenant'))).toMatchObject({
      id: 'tenant-target',
      property_name: 'Target Hotel',
    });
    expect(JSON.parse(localStorage.getItem(ADMIN_TENANT_CONTEXT_KEY))).toMatchObject({
      origin: { tenant: { id: 'tenant-origin' } },
      target: { tenant: { id: 'tenant-target' } },
    });
    expect(isAdminTenantContextActive()).toBe(true);
  });

  it('restores the origin snapshot when the short-lived context expires', () => {
    persistEnteredTenantContext(entered);

    expect(restoreOriginTenantContext({ ...origin.user, name: 'Fresh Platform Admin' })).toBe(true);
    expect(localStorage.getItem(ADMIN_TENANT_CONTEXT_KEY)).toBeNull();
    expect(JSON.parse(localStorage.getItem('tenant'))).toMatchObject({ id: 'tenant-origin' });
    expect(JSON.parse(localStorage.getItem('user'))).toMatchObject({
      tenant_id: 'tenant-origin',
      name: 'Fresh Platform Admin',
    });
  });

  it('reconciles a server-restored origin session without a stale target header', () => {
    persistEnteredTenantContext(entered);

    const reconciled = reconcileAdminTenantContext(
      { ...origin.user, name: 'Canonical Admin' },
      entered.tenant,
      entered.modules,
    );

    expect(reconciled.tenant.id).toBe('tenant-origin');
    expect(reconciled.modules).toEqual(origin.modules);
    expect(localStorage.getItem(ADMIN_TENANT_CONTEXT_KEY)).toBeNull();
  });

  it('clears the context snapshot after an explicit server exit', () => {
    persistEnteredTenantContext(entered);
    persistExitedTenantContext({
      access_token: 'origin-access-token',
      user: origin.user,
      tenant: origin.tenant,
      modules: origin.modules,
    });

    expect(isAdminTenantContextActive()).toBe(false);
    expect(JSON.parse(localStorage.getItem('tenant')).id).toBe('tenant-origin');
  });
});
