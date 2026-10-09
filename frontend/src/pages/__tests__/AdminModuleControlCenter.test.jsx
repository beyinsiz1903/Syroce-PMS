import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AdminModuleControlCenter from '../AdminModuleControlCenter';

vi.mock('axios', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn(), defaults: { headers: { common: {} } } } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

describe('AdminModuleControlCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/entitlements')) return Promise.resolve({ data: { plan_name: 'Mini', subscription_status: 'active' } });
      if (url.endsWith('/usage')) return Promise.resolve({ data: { period_days: 30, events: { reservation_created: 4 }, current_resources: { users: 3, active_users: 2 }, last_activity_at: '2026-10-01T09:15:00Z' } });
      if (url.endsWith('/admin/products')) return Promise.resolve({ data: { products: [] } });
      if (url.endsWith('/setup-tasks')) return Promise.resolve({ data: { tasks: [] } });
      if (url.endsWith('/refund-requests')) return Promise.resolve({ data: { requests: [] } });
      if (url.endsWith('/quote-requests')) return Promise.resolve({ data: { requests: [{ id: 'quote-12345678', product_name: 'Restoran POS', tenant_name: 'Denizli Oteli', user_email: 'admin@example.com', status: 'new' }] } });
      return Promise.resolve({ data: { tenants: [{
        id: 'hotel-1', property_name: 'Denizli Oteli', subscription_tier: 'mini', modules: { pms: true, hr: false },
        module_control_updated_at: '2026-10-01T09:15:00Z', module_control_updated_by_name: 'Merkez Yönetici',
        module_control_changes: { hr: { changed_at: '2026-10-01T09:15:00Z', changed_by_name: 'Merkez Yönetici' } },
      }] } });
    });
    axios.patch.mockResolvedValue({ data: { modules: { pms: true, hr: true } } });
  });

  it('keeps changes in draft until publish is clicked', async () => {
    render(<AdminModuleControlCenter />);
    await screen.findByText('Denizli Oteli');
    const toggle = screen.getByRole('switch', { name: /İnsan Kaynakları.*aç/ });
    fireEvent.click(toggle);
    expect(axios.patch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('publish-module-changes'));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith('/admin/tenants/hotel-1/modules', expect.objectContaining({
      modules: expect.objectContaining({ pms: true, hr: true }),
    })));
  });

  it('shows separate license, setup, integration and usage evidence', async () => {
    render(<AdminModuleControlCenter />);
    await screen.findByText('Denizli Oteli');
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getAllByText('Lisans').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Kurulum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Entegrasyon').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Son 30 günde 4 işlem/).length).toBeGreaterThan(0);
    expect(screen.getByText('Son modül yayını')).toBeInTheDocument();
    expect(screen.getAllByText('Merkez Yönetici').length).toBeGreaterThan(0);
  });

  it('opens the superadmin marketplace price editor', async () => {
    render(<AdminModuleControlCenter />);
    await screen.findByText('Denizli Oteli');
    fireEvent.click(screen.getByTestId('manage-marketplace-prices'));
    expect(await screen.findByText('Modül mağazası fiyat ve sözleşme yönetimi')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith('/module-store/admin/products');
    expect(await screen.findByText('Restoran POS')).toBeInTheDocument();
  });
});
