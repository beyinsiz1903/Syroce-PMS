import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import HousekeepingDashboard from "../../pages/HousekeepingDashboard";
import { EntitlementProvider, useEntitlements } from '../EntitlementContext';
import { ModuleGuardedRoute } from '../../routes/ProtectedRoute';
import POSOutletManagement from '../../components/POSOutletManagement';
import Layout from '../../components/Layout';
import POSDashboard from '../../pages/POSDashboard';

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

// Mock next-themes for Layout

vi.mock('../../context/SimulationContext', () => ({
  useSimulation: () => ({ activeScenario: null, step: 0, mistakes: 0, endSimulation: vi.fn() })
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn() })
}));

// Mock ResizeObserver for some components that might need it
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};


const TestComponent = ({ moduleKey }) => {
  const { hasModule } = useEntitlements();
  return <div data-testid="hasModule">{String(hasModule(moduleKey))}</div>;
};

describe('Frontend Behavior Tests', () => {

  it('Layout: legacy modules={}, entitlements={pos_fnb: basic} -> POS görünür, KDS görünmez', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: {},
          entitlements: { pos_fnb: { editions: ['basic'], features: [], limits: {} } }
        }
      });
      return Promise.resolve({ data: [] });
    });

    // Test for POS visibility in Layout
    const { unmount } = render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <TestComponent moduleKey="pos_fnb" />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('hasModule').textContent).toBe('true');
    });
    unmount();

    // Test for KDS visibility in POSDashboard
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: {},
          entitlements: { pos_fnb: { editions: ['basic'], features: [], limits: {} } }
        }
      });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <POSDashboard />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    expect(screen.queryByText('Mutfak Ekranı')).toBeNull();
  });

  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  it('Layout: pos_fnb=false -> POS metni DOM\'da yok', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({ data: { modules: {}, entitlements: {} } });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <Layout user={{roles: []}} tenant={{id: 'tenant-1'}}>
            <div>Content</div>
          </Layout>
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    // Check if 'POS & F&B' is not in the document
    const posLink = screen.queryByText('POS & F&B');
    expect(posLink).toBeNull();
  });

  it('Layout: basic pakette KDS metni (Mutfak Ekranı) DOM\'da yok, pro\'da var', async () => {
    // We will test this by rendering POSDashboard since "Mutfak Ekranı" is in POSDashboard's quick actions
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: { pos_fnb: true },
          entitlements: { pos_fnb: { features: [], limits: {} } }
        }
      });
      return Promise.resolve({ data: [] }); // For /pos/outlets
    });

    const { unmount } = render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <POSDashboard />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    // "Mutfak Ekranı" shouldn't be there because kds feature is missing
    expect(screen.queryByText('Mutfak Ekranı')).toBeNull();

    unmount();

    // Now test with kds feature
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: { pos_fnb: true },
          entitlements: { pos_fnb: { features: ['kds'], limits: {} } }
        }
      });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <POSDashboard />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    expect(screen.queryByText('Mutfak Ekranı')).not.toBeNull();
  });

  it('ProtectedRoute: basic + KDS URL -> dashboard redirect', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: { modules: { pos_fnb: true }, entitlements: { pos_fnb: { features: [], limits: {} } } }
      });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter initialEntries={['/kds']}>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <Routes>
            <Route path="/app/dashboard" element={<div data-testid="dashboard">Dashboard</div>} />
            <Route
              path="/kds"
              element={
                <ModuleGuardedRoute
                  isAuthenticated={true}
                  moduleKey="pos_fnb"
                  featureKey="kds"
                  element={<div data-testid="kds-page">KDS Page</div>}
                />
              }
            />
          </Routes>
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    expect(screen.queryByTestId('kds-page')).toBeNull();
    expect(screen.getByTestId('dashboard')).toBeDefined();
  });

  it('POSOutletManagement: used=limit -> Yeni Satış Noktası disabled', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: { pos_fnb: true },
          entitlements: { pos_fnb: { features: [], limits: { outlets: 1 } } }
        }
      });
      if (url === '/pos/outlets') return Promise.resolve({ data: [{ _id: '1', name: 'Outlet 1' }] });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <POSOutletManagement onChange={vi.fn()} />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    // Check button disabled state
    await waitFor(() => {
      const btn = screen.getByTestId('button-new-outlet');
      expect(btn.disabled).toBe(true);
    });
  });

  it('POSOutletManagement: used<limit -> buton aktif', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/subscription/current') return Promise.resolve({
        data: {
          modules: { pos_fnb: true },
          entitlements: { pos_fnb: { features: [], limits: { outlets: 5 } } }
        }
      });
      if (url === '/pos/outlets') return Promise.resolve({ data: [{ _id: '1', name: 'Outlet 1' }] });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <POSOutletManagement onChange={vi.fn()} />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await act(async () => { await new Promise(r => setTimeout(r, 0)); });

    await waitFor(() => {
      const btn = screen.getByTestId('button-new-outlet');
      expect(btn.disabled).toBe(false);
    });
  });

  it('Logout/tenant clear -> localStorage entitlement kaydı yok', async () => {
    // Prime cache with some data
    window.localStorage.setItem("entitlements", JSON.stringify({
      tenantId: "tenant-1",
      modules: { pos_fnb: true },
      entitlements: {}
    }));

    const LogoutTestComponent = () => {
      const { clearEntitlements } = useEntitlements();
      return <button onClick={() => clearEntitlements()} data-testid="logout-btn">Logout</button>;
    };

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <LogoutTestComponent />
        </EntitlementProvider>
      </MemoryRouter>
    );

    const btn = screen.getByTestId('logout-btn');
    fireEvent.click(btn);

    expect(window.localStorage.getItem("entitlements")).toBeNull();
  });

  it('HR modülü yoksa İK menüsü görünmez', async () => {
    axios.get.mockImplementation(() => Promise.resolve({ data: {
      modules: { 'frontdesk': true },
      entitlements: {}
    } }));

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <Layout tenant={{}} currentModule="dashboard" onLogout={() => {}}>
            <div>Test</div>
          </Layout>
        </EntitlementProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.queryByTestId('nav-hr_hub-button')).toBeNull();
    });
  });

  it('HR modülü var ancak payroll yetkisi yoksa, Bordro (payroll) sekmesi kilitlenir/gizlenir', async () => {
    // Basic edition, hr var ama payroll yok
    axios.get.mockImplementation(() => Promise.resolve({ data: {
      modules: { 'hr': true },
      entitlements: {
        hr: { editions: ['basic'], features: ['shift'], limits: { employees: 50 } }
      }
    } }));

    const { default: HRComplete } = await import('@/pages/HRComplete');

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <HRComplete tenant={{}} user={{}} />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      // should have attendance tab
      expect(screen.getByTestId('tab-attendance')).not.toBeNull();
      // should NOT have payroll tab
      expect(screen.queryByTestId('tab-payroll')).toBeNull();
      // should NOT have leave tab
      expect(screen.queryByTestId('tab-leave')).toBeNull();
      expect(screen.queryByTestId('tab-recruitment')).toBeNull();
    });
  });

  it('HR Pro paketinde (payroll yetkisi olan), Bordro (payroll) sekmesi gösterilir', async () => {
    axios.get.mockImplementation(() => Promise.resolve({ data: {
      modules: { 'hr': true },
      entitlements: {
        hr: { editions: ['pro'], features: ['shift', 'payroll', 'leave', 'recruitment'], limits: { employees: 200 } }
      }
    } }));

    const { default: HRComplete } = await import('@/pages/HRComplete');

    render(
      <MemoryRouter>
        <EntitlementProvider currentTenantId="tenant-1" isSuperAdmin={false}>
          <HRComplete tenant={{}} user={{}} />
        </EntitlementProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('tab-attendance')).not.toBeNull();
      expect(screen.getByTestId('tab-payroll')).not.toBeNull();
      expect(screen.getByTestId('tab-leave')).not.toBeNull();
      expect(screen.getByTestId('tab-recruitment')).not.toBeNull();
    });
  });

  const TestMiceComponent = () => {
    const { entitlements, getLimit, hasFeature, hasModule } = useEntitlements();

    if (!entitlements) return <div data-testid="loading">Yükleniyor...</div>;

    const canSeeMice = hasModule('mice');
    const hasBanquet = entitlements?.mice?.features?.includes('banquet_operations');

    const eventsLimit = entitlements?.mice?.limits?.concurrent_events ?? 0;
    const eventsUsage = entitlements?.mice?.usage?.concurrent_events ?? 0;
    const eventsLimitHit = eventsLimit > 0 && eventsUsage >= eventsLimit;

    return (
        <div>
            {canSeeMice ? <div data-testid="mice-menu">MICE Menüsü</div> : <div data-testid="no-mice">Gizli</div>}
            {hasBanquet ? <button data-testid="beo-btn">BEO Yazdır</button> : <span data-testid="no-beo">BEO Yok</span>}
            <button data-testid="new-event-btn" disabled={eventsLimitHit}>Yeni Etkinlik</button>
        </div>
    );
  };

  test("Pro tier shows MICE, BEO button, and disables New Event button if limit hit", async () => {
      axios.get.mockResolvedValue({
          data: {
              tenant_id: "t1",
              modules: { mice: true, pos_fnb: true },
              entitlements: {
                  mice: {
                      tier: "pro",
                      features: ["banquet_operations", "proposals_contracts"],
                      limits: { concurrent_events: 50 },
                      usage: { concurrent_events: 50 }
                  }
              }
          }
      });

      render(
          <MemoryRouter>
              <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                  <TestMiceComponent />
              </EntitlementProvider>
          </MemoryRouter>
      );

      await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

      expect(screen.getByTestId("mice-menu")).not.toBeNull();
      expect(screen.getByTestId("beo-btn")).not.toBeNull();
      expect(screen.getByTestId("new-event-btn").disabled).toBe(true);
  });

  test("Basic tier hides BEO button", async () => {
      axios.get.mockResolvedValue({
          data: {
              tenant_id: "t1",
              modules: { mice: true },
              entitlements: {
                  mice: {
                      tier: "basic",
                      features: [],
                      limits: { concurrent_events: 5 },
                      usage: { concurrent_events: 2 }
                  }
              }
          }
      });

      render(
          <MemoryRouter>
              <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                  <TestMiceComponent />
              </EntitlementProvider>
          </MemoryRouter>
      );

      await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

      expect(screen.getByTestId("mice-menu")).not.toBeNull();
      expect(screen.getByTestId("no-beo")).not.toBeNull();
      expect(screen.queryByTestId("beo-btn")).toBeNull();
      expect(screen.getByTestId("new-event-btn").disabled).toBe(false);
  });

  test("Hides MICE menu if module not enabled", async () => {
      axios.get.mockResolvedValue({
          data: {
              tenant_id: "t1",
              modules: { hotel_rooms: true },
              entitlements: {}
          }
      });

      render(
          <MemoryRouter>
              <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                  <TestMiceComponent />
              </EntitlementProvider>
          </MemoryRouter>
      );

      await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

      expect(screen.getByTestId("no-mice")).not.toBeNull();
      expect(screen.queryByTestId("mice-menu")).toBeNull();
  });


  // --------------------------------------------------------------------------------
  // HOUSEKEEPING ENTITLEMENT TESTS
  // --------------------------------------------------------------------------------

  it('renders HousekeepingDashboard features for PRO users', async () => {
      axios.get.mockImplementation((url) => {
          if (url === '/subscription/current') {
              return Promise.resolve({
                  data: {
                      modules: { housekeeping: true },
                      entitlements: {
                          housekeeping: {
                              features: ['advanced_reporting', 'quality_control', 'mobile_app']
                          }
                      }
                  }
              });
          }
          if (url === '/housekeeping/room-status') {
              return Promise.resolve({ data: { rooms: [{ id: '1' }], total_rooms: 1 } });
          }
          return Promise.resolve({ data: {} });
      });

      render(
          <MemoryRouter>
              <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                  <HousekeepingDashboard />
              </EntitlementProvider>
          </MemoryRouter>
      );

      await waitFor(() => {
          expect(screen.getByTestId("page-housekeeping")).toBeInTheDocument();
      });

      // Assert Pro features are visible
      await waitFor(() => expect(screen.getByText("hkDashboard.detailedReports")).toBeInTheDocument());
      // Test mobile button is enabled
      const mobileBtn = screen.getByTestId("hk-quick-mobile");
      expect(mobileBtn).not.toBeDisabled();
  });

  it('hides HousekeepingDashboard features for BASIC users', async () => {
      axios.get.mockImplementation((url) => {
          if (url === '/subscription/current') {
              return Promise.resolve({
                  data: {
                      modules: { housekeeping: true },
                      entitlements: {
                          housekeeping: {
                              features: [] // Basic subscription
                          }
                      }
                  }
              });
          }
          if (url === '/housekeeping/room-status') {
              return Promise.resolve({ data: { rooms: [{ id: '1' }], total_rooms: 1 } });
          }
          return Promise.resolve({ data: {} });
      });

      render(
          <MemoryRouter>
              <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                  <HousekeepingDashboard />
              </EntitlementProvider>
          </MemoryRouter>
      );

      await waitFor(() => {
          expect(screen.getByTestId("page-housekeeping")).toBeInTheDocument();
      });

      // Assert Pro features are hidden
      expect(screen.queryByText("hkDashboard.detailedReports")).not.toBeInTheDocument();
      // Test mobile button is disabled
      const mobileBtn = screen.getByTestId("hk-quick-mobile");
      expect(mobileBtn).toBeDisabled();
  });

});
