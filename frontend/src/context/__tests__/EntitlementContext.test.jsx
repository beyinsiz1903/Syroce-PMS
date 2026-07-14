import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { EntitlementProvider, useEntitlements } from '../EntitlementContext';

vi.mock('axios');

const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = value.toString(); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

const TestComponent = ({ moduleKey, featureKey, limitKey }) => {
  const { hasModule, hasFeature, getLimit, loading, loaded, error, tenantId } = useEntitlements();
  return (
    <div>
      <div data-testid="loading">{loading.toString()}</div>
      <div data-testid="loaded">{loaded.toString()}</div>
      <div data-testid="error">{error || 'none'}</div>
      <div data-testid="tenantId">{tenantId || 'none'}</div>
      <div data-testid="hasModule">{hasModule(moduleKey).toString()}</div>
      <div data-testid="hasFeature">{hasFeature(moduleKey, featureKey).toString()}</div>
      <div data-testid="limit">{getLimit(moduleKey, limitKey)}</div>
    </div>
  );
};

describe('EntitlementContext', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  it('shows loading initially and hasModule returns false for strict modules', async () => {
    let resolveAxios;
    axios.get.mockImplementation(() => new Promise((resolve) => {
      resolveAxios = resolve;
    }));

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
        <TestComponent moduleKey="pos_fnb" />
      </EntitlementProvider>
    );

    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('hasModule').textContent).toBe('false');

    await act(async () => {
      resolveAxios({ data: { modules: { pos_fnb: true }, entitlements: {} } });
    });

    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('hasModule').textContent).toBe('true');
  });

  it('denies access if pos_fnb is missing (strict module)', async () => {
    axios.get.mockResolvedValue({ data: { modules: {}, entitlements: {} } });

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
        <TestComponent moduleKey="pos_fnb" />
      </EntitlementProvider>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.getByTestId('hasModule').textContent).toBe('false'); // Missing strict module
  });

  it('allows access to non-strict modules if missing', async () => {
    axios.get.mockResolvedValue({ data: { modules: {}, entitlements: {} } });

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
        <TestComponent moduleKey="some_other_module" />
      </EntitlementProvider>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.getByTestId('hasModule').textContent).toBe('true');
  });

  it('handles KDS feature for pro and basic', async () => {
    axios.get.mockResolvedValue({
      data: {
        modules: { pos_fnb: true },
        entitlements: { pos_fnb: { features: ['kds'], limits: { outlets: 5 } } }
      }
    });

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
        <TestComponent moduleKey="pos_fnb" featureKey="kds" limitKey="outlets" />
      </EntitlementProvider>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.getByTestId('hasModule').textContent).toBe('true');
    expect(screen.getByTestId('hasFeature').textContent).toBe('true');
    expect(screen.getByTestId('limit').textContent).toBe('5');
  });

  it('clears cache on tenant mismatch without flashing old data', async () => {
    // Prime cache with tenant-1
    window.localStorage.setItem("entitlements", JSON.stringify({
      tenantId: "tenant-1",
      modules: { pos_fnb: true },
      entitlements: {}
    }));

    let resolveAxios;
    axios.get.mockImplementation(() => new Promise((resolve) => { resolveAxios = resolve; }));

    render(
      <EntitlementProvider currentTenantId="tenant-2" isSuperAdmin={false}>
        <TestComponent moduleKey="pos_fnb" />
      </EntitlementProvider>
    );

    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('hasModule').textContent).toBe('false');

    await act(async () => {
      resolveAxios({ data: { modules: {}, entitlements: {} } });
      await new Promise(r => setTimeout(r, 0));
    });

    // After fetch
    expect(screen.getByTestId('tenantId').textContent).toBe('tenant-2');
    expect(screen.getByTestId('hasModule').textContent).toBe('false'); // pos_fnb is missing
  });

  it('super_admin bypasses restrictions', async () => {
    axios.get.mockResolvedValue({ data: { modules: {}, entitlements: {} } });

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={true}>
        <TestComponent moduleKey="pos_fnb" featureKey="kds" limitKey="outlets" />
      </EntitlementProvider>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.getByTestId('hasModule').textContent).toBe('true');
    expect(screen.getByTestId('hasFeature').textContent).toBe('true');
    // Note: getLimit for super admin doesn't bypass, it just returns what's there (0 in this case)
  });

  it('handles API error by denying access and setting error state', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: "403 Forbidden" } } });

    render(
      <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
        <TestComponent moduleKey="pos_fnb" />
      </EntitlementProvider>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('hasModule').textContent).toBe('false');
    expect(screen.getByTestId('error').textContent).toBe('403 Forbidden');
  });
});
