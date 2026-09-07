import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import TenantUsers from './TenantUsers';
import { NAV_ITEMS } from '@/config/navItems';
import { moduleScopesForNavItem, moduleScopesForPath } from '@/utils/moduleAccess';
import { securityAdminRoutes } from '@/routes/sections/securityAdmin';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/components/UserProvisionDialog', () => ({ default: ({ onCreated, disabled }) =>
  <button disabled={disabled} onClick={onCreated}>Kullanıcı Ekle</button> }));
const admin = { id: 'admin', tenant_id: 'hotel', role: 'admin', module_scopes: [] };
describe('tenant user administration independent of HR', () => {
  beforeEach(() => {
    axios.get.mockReset();
    axios.get.mockResolvedValue({ data: { users: [{ id: 'one', name: 'QA Finans', email: 'qa@example.com', role: 'finance' }] } });
  });
  it('lists tenant users for an admin without module access and refreshes after creation', async () => {
    render(<TenantUsers user={admin} />);
    await screen.findByText('QA Finans');
    expect(axios.get).toHaveBeenCalledWith('/admin/tenant-users', expect.objectContaining({ signal: expect.anything() }));
    expect(axios.get.mock.calls.every(([url]) => url === '/admin/tenant-users')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Kullanıcı Ekle' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  });
  it.each(['front_desk', 'finance', 'supervisor', 'staff', undefined])('denies %s before fetching or creating', role => {
    render(<TenantUsers user={{ ...admin, role }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('yalnızca otel yöneticilerine');
    expect(screen.queryByRole('button', { name: 'Kullanıcı Ekle' })).not.toBeInTheDocument();
    expect(axios.get).not.toHaveBeenCalled();
  });
  it('clears the list and disables creation when the API denies access', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Yetkiniz yok' } } });
    render(<TenantUsers user={admin} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Yetkiniz yok');
    expect(screen.getByRole('button', { name: 'Kullanıcı Ekle' })).toBeDisabled();
  });
  it('has an admin-only menu without HR entitlement or module-scope requirement', () => {
    const item = NAV_ITEMS.find(item => item.key === 'tenant_users');
    expect(item.allowedRoles).toEqual(['admin', 'super_admin']);
    expect(item.moduleKey).toBeUndefined();
    expect(item.requireSuperAdmin).not.toBe(true);
    expect(moduleScopesForNavItem(item)).toEqual([]);
    expect(moduleScopesForPath(item.path)).toEqual([]);
    const routes = securityAdminRoutes({ p: component => ({ component }), pa: component => ({ component, requireSuperAdmin: true }) });
    expect(routes.find(route => route.path === item.path).requireSuperAdmin).not.toBe(true);
    expect(routes.find(route => route.path === '/admin/user-roles').requireSuperAdmin).toBe(true);
  });
});
