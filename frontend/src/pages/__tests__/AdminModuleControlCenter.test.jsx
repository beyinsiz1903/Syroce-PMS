import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    expect(screen.getByLabelText('Aşama')).toHaveValue('new');
    expect(screen.getByLabelText('Sorumlu')).toBeInTheDocument();
    expect(screen.getByLabelText('Takip tarihi')).toBeInTheDocument();
    expect(screen.getByLabelText('Yönetici notu')).toBeInTheDocument();
  });

  it('says why an enabled module is not in the menu (property allow-list)', async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/admin/tenants')) return Promise.resolve({ data: { tenants: [{
        id: 'hotel-2', property_name: 'Sapanca Oteli', subscription_tier: 'basic',
        modules: { pms: true, channel_manager: true, agency_extranet: true },
        visible_nav_items: ['dashboard', 'incoming_agency_contracts'],
      }] } });
      return Promise.resolve({ data: {} });
    });
    render(<AdminModuleControlCenter />);
    await screen.findByText('Sapanca Oteli');
    fireEvent.change(screen.getByPlaceholderText(/ara/i), { target: { value: 'Acente Extranet' } });
    const status = await screen.findByTestId('module-menu-status');
    expect(status).toHaveTextContent(/1\/\d+ sayfa görünür/);
    expect(status).toHaveTextContent('Tesis profilinin menü listesinde yok');
  });

  it.each([
    [{}, true, 'Pakette yok'],                              // plan default only: not an admin choice
    [{ maintenance: false }, true, 'Yönetici modülü kapattı'], // stored choice
    [{}, false, 'Modül kapalı'],                            // older record: origin unknown, stay neutral
  ])('tells "not in plan" from "disabled by admin" (preferences %o, known %s)', async (preferences, known, reason) => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/admin/tenants')) return Promise.resolve({ data: { tenants: [{
        id: 'hotel-3', property_name: 'Mini Otel', subscription_tier: 'mini',
        modules: { pms: true, maintenance: false }, module_preferences: preferences, module_preferences_known: known,
      }] } });
      return Promise.resolve({ data: {} });
    });
    render(<AdminModuleControlCenter />);
    await screen.findByText('Mini Otel');
    fireEvent.change(screen.getByPlaceholderText(/ara/i), { target: { value: 'Bakım Yönetimi' } });
    const status = await screen.findByTestId('module-menu-status');
    expect(status).toHaveTextContent(reason);
  });

  it("shows each module's real setup state and what is missing", async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/admin/tenants')) return Promise.resolve({ data: { tenants: [{
        id: 'hotel-4', property_name: 'Kartepe', subscription_tier: 'professional', modules: { pms: true, spa: true },
      }] } });
      if (url.endsWith('/module-readiness')) return Promise.resolve({ data: { modules: {
        spa: { module: 'spa', status: 'incomplete', setup: [{ key: 'spa_therapists', label: 'Terapist', ok: false, path: '/spa-wellness' }], usage: [] },
      } } });
      return Promise.resolve({ data: {} });
    });
    render(<AdminModuleControlCenter />);
    await screen.findByText('Kartepe');
    expect(axios.get).toHaveBeenCalledWith('/admin/tenants/hotel-4/module-readiness');
    fireEvent.change(screen.getByPlaceholderText(/ara/i), { target: { value: 'SPA' } });
    expect(await screen.findByTestId('module-setup-spa')).toHaveTextContent('Kurulum eksik (1)');
    expect(screen.getByTestId('module-missing-spa')).toHaveTextContent('Terapist');
  });

  it('keeps licence/usage visible when readiness fails and can retry independently', async () => {
    const original = axios.get.getMockImplementation();
    let fail = true;
    axios.get.mockImplementation(url => {
      if (url.endsWith('/module-readiness')) return fail
        ? Promise.reject(new Error('readiness offline'))
        : Promise.resolve({ data: { modules: { pms: { status: 'idle', setup: [], usage: [] } } } });
      return original(url);
    });
    render(<AdminModuleControlCenter />);
    expect(await screen.findByTestId('readiness-load-error')).toHaveTextContent('Lisans ve kullanım özeti etkilenmedi');
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getAllByText(/Son 30 günde 4 işlem/).length).toBeGreaterThan(0);
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Kurulum kontrollerini yenile' }));
    await waitFor(() => expect(screen.queryByTestId('readiness-load-error')).not.toBeInTheDocument());
    expect(await screen.findByTestId('module-setup-pms')).toHaveTextContent('Kuruldu · son dönemde kullanılmıyor');
  });

  it('does not present failed checks as missing configuration', async () => {
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.endsWith('/module-readiness') ? Promise.resolve({ data: { modules: {
      pms: { status: 'unknown', setup: [{ key: 'rooms', label: 'Odalar tanımlı', ok: null }], usage: [] },
    } } }) : original(url));
    render(<AdminModuleControlCenter />);
    expect(await screen.findByTestId('module-setup-pms')).toHaveTextContent('Durum doğrulanamadı');
    expect(screen.queryByTestId('module-missing-pms')).not.toBeInTheDocument();
  });

  it('never replaces the selected hotel setup with a previous hotel response', async () => {
    let delayed = false;
    const replies = [];
    axios.get.mockImplementation(url => {
      if (url.endsWith('/admin/tenants')) return Promise.resolve({ data: { tenants: [
        { id: 'first', property_name: 'İlk Otel', modules: { spa: true } },
        { id: 'second', property_name: 'İkinci Otel', modules: { spa: true } },
      ] } });
      if (url.includes('/first/module-readiness')) return delayed ? new Promise(resolve => replies.push(resolve))
        : Promise.resolve({ data: { modules: { spa: { status: 'active', setup: [], usage: [] } } } });
      if (url.includes('/second/module-readiness')) return Promise.resolve({ data: { modules: { spa: {
        status: 'incomplete', setup: [{ key: 'rooms', label: 'İkinci otelin SPA odası eksik', ok: false }], usage: [],
      } } } });
      return Promise.resolve({ data: {} });
    });
    render(<AdminModuleControlCenter />);
    fireEvent.change(screen.getByPlaceholderText(/ara/i), { target: { value: 'SPA' } });
    expect(await screen.findByTestId('module-setup-spa')).toHaveTextContent('Kuruldu · kullanımda');
    delayed = true;
    fireEvent.click(screen.getByRole('button', { name: 'Kurulum kontrollerini yenile' }));
    await waitFor(() => expect(replies.length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: /İkinci Otel/ }));
    expect(await screen.findByTestId('module-missing-spa')).toHaveTextContent('İkinci otelin SPA odası eksik');
    await act(async () => replies.forEach(resolve => resolve({ data: { modules: { spa: { status: 'active', setup: [], usage: [] } } } })));
    expect(screen.getByTestId('module-setup-spa')).toHaveTextContent('Kurulum eksik (1)');
    expect(screen.getByTestId('module-missing-spa')).toHaveTextContent('İkinci otelin SPA odası eksik');
  });
});
