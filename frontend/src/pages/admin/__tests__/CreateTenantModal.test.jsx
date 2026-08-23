import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CreateTenantModal from '@/pages/admin/CreateTenantModal';
import axios from 'axios';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const CAMPING_PROFILE = {
  key: 'camping',
  name_tr: 'Kamp Alanı / Glamping',
  description_tr: 'Kamp, glamping ve doğa konaklama tesisi.',
  icon: 'Tent',
  room_range: { min: 5, max: 100 },
  typical_staff: 3,
  recommended_tier: 'basic',
  dashboard_layout: 'standard',
  modules: {
    pms: true,
    reservation_calendar: true,
    dashboard: true,
    guests: true,
    housekeeping: true,
    basic_reporting: true,
    settings: true,
  },
};

const reachInstallationSummary = async () => {
  render(
    <CreateTenantModal
      open
      onOpenChange={vi.fn()}
      onSuccess={vi.fn()}
    />,
  );

  await waitFor(() => expect(screen.getByText('Kamp Alanı / Glamping')).toBeInTheDocument());
  fireEvent.click(screen.getByText('Kamp Alanı / Glamping'));
  fireEvent.click(screen.getByRole('button', { name: /Devam/ }));

  fireEvent.change(screen.getByTestId('create-tenant-property-name'), { target: { value: 'Doğa Otel' } });
  fireEvent.change(screen.getByTestId('create-tenant-admin-name'), { target: { value: 'Otel Müdürü' } });
  fireEvent.change(screen.getByTestId('create-tenant-email'), { target: { value: 'mudur@example.com' } });
  fireEvent.change(screen.getByTestId('create-tenant-password'), { target: { value: 'guvenli123' } });
  fireEvent.change(screen.getByTestId('create-tenant-phone'), { target: { value: '+90 555 111 2233' } });
  fireEvent.change(screen.getByTestId('create-tenant-address'), { target: { value: 'Kartepe, Kocaeli' } });
  fireEvent.click(screen.getByTestId('create-tenant-next-modules'));
};

describe('CreateTenantModal professional module wizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockImplementation((url) => {
      if (url === '/admin/property-types') {
        return Promise.resolve({ data: { property_types: [CAMPING_PROFILE] } });
      }
      if (url === '/admin/chains') {
        return Promise.resolve({ data: { chains: [] } });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
  });

  it('shows a concise plan summary instead of the full feature-flag catalogue', async () => {
    await reachInstallationSummary();

    expect(screen.getByTestId('tenant-module-summary')).toBeInTheDocument();
    expect(screen.getByText('Önerilen kurulum hazır')).toBeInTheDocument();
    expect(screen.getByText('Ön Büro & Rezervasyon')).toBeInTheDocument();
    expect(screen.getByText('Misafir & Operasyon')).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-module-customization')).not.toBeInTheDocument();

    expect(screen.queryByText('PMS Çekirdek')).not.toBeInTheDocument();
    expect(screen.queryByText('PMS Alt Sekmeleri')).not.toBeInTheDocument();
    expect(screen.queryByText('System Health')).not.toBeInTheDocument();
  });

  it('keeps only real optional products behind an explicit customization control', async () => {
    await reachInstallationSummary();

    fireEvent.click(screen.getByTestId('tenant-module-customize-toggle'));

    expect(screen.getByTestId('tenant-module-customization')).toBeInTheDocument();
    expect(screen.getByText('Enterprise Modüller')).toBeInTheDocument();
    expect(screen.getByText('AI Modülleri')).toBeInTheDocument();
    expect(screen.getByText('Add-on Modüller (Ekstra Ücretli)')).toBeInTheDocument();

    expect(screen.queryByText('PMS Alt Sekmeleri')).not.toBeInTheDocument();
    expect(screen.queryByText('Rapor Listesi (Excel Raporları)')).not.toBeInTheDocument();
    expect(screen.queryByText('System Health')).not.toBeInTheDocument();
  });

  it('prices paid add-ons live and automatically enables the AI parent module', async () => {
    await reachInstallationSummary();
    expect(screen.getByTestId('commercial-quote-summary')).toHaveTextContent('€79/ay');

    fireEvent.click(screen.getByTestId('tenant-module-customize-toggle'));
    fireEvent.click(screen.getByRole('button', { name: /AI Modülleri/ }));
    fireEvent.click(screen.getByLabelText(/AI Chatbot/));

    expect(screen.getByTestId('commercial-quote-summary')).toHaveTextContent('€128/ay');
    axios.post.mockResolvedValue({ data: { success: true } });
    fireEvent.click(screen.getByTestId('create-tenant-submit'));
    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    const payload = axios.post.mock.calls[0][1];
    expect(payload.modules.ai).toBe(true);
    expect(payload.commercial_quote.list_monthly_total).toBe(128);
    expect(payload.commercial_quote.line_items).toEqual(expect.arrayContaining([expect.objectContaining({ module_key: 'ai_chatbot', monthly: 49 })]));
  });

  it('requires a reason when the final price is overridden', async () => {
    await reachInstallationSummary();
    fireEvent.change(screen.getByTestId('final-monthly-total'), { target: { value: '70' } });
    fireEvent.click(screen.getByTestId('create-tenant-submit'));
    expect(await screen.findByText('Liste fiyatı değiştirildiğinde fiyat değişikliği nedeni zorunludur')).toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });
});
