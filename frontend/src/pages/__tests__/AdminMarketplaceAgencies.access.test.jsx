import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import AdminMarketplaceAgencies, { startAgencyPortalContext } from '../AdminMarketplaceAgencies';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/routes/preload', () => ({ preloadRoute: vi.fn() }));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminMarketplaceAgencies />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function fillNewAgency() {
  await screen.findByText('Acente Yönetimi');
  fireEvent.click(screen.getByTestId('create-marketplace-agency'));
  fireEvent.change(screen.getByLabelText('Acente adı'), { target: { value: 'Güvenli Travel' } });
  fireEvent.change(screen.getByLabelText('İletişim e-postası'), { target: { value: 'api@example.com' } });
}

describe('AdminMarketplaceAgencies access lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { agencies: [] } });
    axios.post.mockResolvedValue({ data: { agency: { id: 'agency-1' }, api_key: null } });
  });

  it('opens a passwordless audited agency context without replacing the hotel admin token', async () => {
    axios.post.mockResolvedValue({ data: { token: 'short-lived-agency-token', portal_path: '/agency-portal' } });
    localStorage.setItem('access_token', 'existing-superadmin-token');
    const navigate = vi.fn();

    await startAgencyPortalContext('agency-1', navigate);

    expect(axios.post).toHaveBeenCalledWith('/marketplace/v1/admin/agencies/agency-1/portal-context');
    expect(localStorage.getItem('access_token')).toBe('existing-superadmin-token');
    expect(localStorage.getItem('agency_token')).toBe('short-lived-agency-token');
    expect(localStorage.getItem('agency_portal_mode')).toBe('marketplace');
    expect(sessionStorage.getItem('agency_admin_return_path')).toBe('/admin/marketplace/agencies');
    expect(navigate).toHaveBeenCalledWith('/agency-portal');
  });

  it('defaults new agencies to portal-only and does not create an unnecessary secret', async () => {
    renderPage();
    await fillNewAgency();

    expect(screen.getByText(/API anahtarı yalnızca acentenin kendi yazılımını Syroce'a bağlayacağı zaman gerekir/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Teknik API entegrasyonu/ })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      '/marketplace/v1/admin/agencies',
      expect.objectContaining({ issue_api_key: false }),
    ));
    expect(screen.queryByText('Teknik API anahtarı oluşturuldu')).not.toBeInTheDocument();
  });

  it('creates and explains a recoverable-once key only after explicit opt-in', async () => {
    axios.post.mockResolvedValue({
      data: { api_key: 'syroce_mkt_once', warning: 'yalnızca bir kez' },
    });
    renderPage();
    await fillNewAgency();

    fireEvent.click(screen.getByRole('button', { name: /Teknik API entegrasyonu/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    expect(await screen.findByText('Teknik API anahtarı oluşturuldu')).toBeInTheDocument();
    expect(screen.getByText(/insan kullanıcı girişi değildir/)).toBeInTheDocument();
    expect(axios.post).toHaveBeenCalledWith(
      '/marketplace/v1/admin/agencies',
      expect.objectContaining({ issue_api_key: true, api_key_label: 'Ana entegrasyon' }),
    );
  });

  it('does not present an unused key as a verified live integration', async () => {
    axios.get.mockResolvedValue({
      data: {
        agencies: [{
          id: 'agency-1', name: 'Yeni Entegrasyon', status: 'active', contact_email: 'api@example.com',
          api_access: { active: true, key_prefix: 'syroce_mkt_...', usage_count: 0, last_used_at: null },
          portal_access: { count: 0 },
        }],
      },
    });
    renderPage();

    expect(await screen.findByText('API Etkinleştirme bekliyor')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Erişim/ }));
    expect(await screen.findByText('Anahtar oluşturuldu; henüz doğrulanmış bir API isteği görülmedi.')).toBeInTheDocument();
    expect(screen.getByText(/ilk başarılı istekten sonra durum otomatik olarak “Kullanımda” olur/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'B2B API belgelerini aç →' })).toHaveAttribute('href', '/b2b/docs');
  });
});
