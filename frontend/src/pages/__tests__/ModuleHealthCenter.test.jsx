import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import ModuleHealthCenter from '../ModuleHealthCenter';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));

const snapshot = {
  generated_at: '2026-10-04T10:20:00Z',
  telemetry_window_days: 30,
  subscription: { plan: 'enterprise', status: 'active' },
  summary: { total: 2, healthy: 1, unknown: 0, setup_required: 0, attention: 0, error: 1 },
  modules: [
    {
      key: 'channel_manager', name: 'Kanal yöneticisi', status: 'healthy', installation_status: 'installed',
      license_status: 'licensed', integration_status: 'configured', last_used_at: '2026-10-04T09:20:00Z', last_error: null,
      providers: [{ provider: 'hotelrunner', connected: true, operational_status: { key: 'production', label: 'Üretimde', intent: 'success' } }],
    },
    {
      key: 'whatsapp', name: 'WhatsApp Business', status: 'error', installation_status: 'installed',
      license_status: 'licensed', integration_status: 'configured', last_used_at: null, last_error: 'Sağlayıcı bağlantısı kesildi', last_error_at: '2026-10-04T09:40:00Z',
    },
  ],
};

describe('ModuleHealthCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: snapshot });
  });

  it('renders real license, setup, connection, usage, error and production evidence', async () => {
    render(<ModuleHealthCenter />);
    expect(await screen.findByText('Kanal yöneticisi')).toBeInTheDocument();
    expect(screen.getAllByText('Üretimde sağlıklı').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bağlantı yapılandırılmış').length).toBeGreaterThan(0);
    expect(screen.getByText('hotelrunner: Üretimde')).toBeInTheDocument();
    expect(screen.getByText('Sağlayıcı bağlantısı kesildi')).toBeInTheDocument();
    expect(screen.getAllByText('Hata var').length).toBeGreaterThan(0);
    expect(axios.get).toHaveBeenCalledWith('/module-health');
  });

  it('filters rows by the selected health status', async () => {
    render(<ModuleHealthCenter />);
    await screen.findByText('WhatsApp Business');
    fireEvent.click(screen.getByRole('button', { name: 'Hata' }));
    expect(screen.getByText('WhatsApp Business')).toBeInTheDocument();
    expect(screen.queryByText('Kanal yöneticisi')).not.toBeInTheDocument();
  });

  it('uses the shared forbidden state when diagnostics permission is missing', async () => {
    axios.get.mockRejectedValueOnce({ response: { status: 403 } });
    render(<ModuleHealthCenter />);
    await waitFor(() => expect(screen.getByText('Bu ekran için yetkiniz yok')).toBeInTheDocument());
  });
});
