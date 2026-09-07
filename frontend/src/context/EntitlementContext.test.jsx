import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { EntitlementProvider, useEntitlements } from './EntitlementContext';
import { hasAnyModuleAccess, moduleScopesForNavItem } from '@/utils/moduleAccess';
import { NAV_ITEMS } from '@/config/navItems';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
const hr = NAV_ITEMS.find(item => item.key === 'hr_hub');

function Probe({ scopes }) {
  const { hasModule, loading } = useEntitlements();
  if (loading) return <div>loading</div>;
  const visible = hasModule(hr.moduleKey) && hasAnyModuleAccess({ role: 'admin', module_scopes: scopes }, moduleScopesForNavItem(hr));
  return <div>{visible ? 'HR visible' : 'HR hidden'}</div>;
}

describe('HR tenant menu entitlement', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

  it.each([
    [{ hr: true }, ['hr'], 'HR visible'],
    [{ hr: false }, ['hr'], 'HR hidden'],
    [{}, ['hr'], 'HR hidden'],
    [{ hr: true }, ['frontdesk'], 'HR hidden'],
  ])('honors explicit module and role scope: %j / %j', async (modules, scopes, expected) => {
    axios.get.mockResolvedValue({ data: { modules, entitlements: {} } });
    // Hotel impersonation intentionally does not use the platform-admin bypass.
    render(<EntitlementProvider currentTenantId="qa-hotel" isSuperAdmin={false}><Probe scopes={scopes} /></EntitlementProvider>);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
});
