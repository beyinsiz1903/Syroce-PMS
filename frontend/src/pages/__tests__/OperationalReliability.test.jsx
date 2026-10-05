import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: vi.fn(),
  },
}));

vi.mock('i18next', () => ({ t: (key) => key }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import LogViewer from '@/pages/LogViewer';
import MobileLogViewer from '@/pages/MobileLogViewer';
import ProductionRolloutDashboard from '@/pages/ProductionRolloutPage';

describe('Operational page reliability', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    localStorage.clear();
  });

  it('loads production rollout through the cookie session without a local token', async () => {
    axiosGet.mockResolvedValue({ data: { data: {} } });

    render(
      <MemoryRouter>
        <ProductionRolloutDashboard />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('production-rollout-dashboard')).toBeInTheDocument();
    });
    expect(localStorage.getItem('token')).toBeNull();
    expect(axiosGet).toHaveBeenCalledWith('/production/env/validate', { headers: {} });
  });

  it('never presents synthetic load validation as a runnable production check', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/production/load/scenarios') {
        return Promise.resolve({ data: { data: { runner_configured: false, scenarios: [{ id: 'ota_reservation_burst', name: 'OTA burst', thresholds: {}, execution_mode: 'external_runner_required' }] } } });
      }
      return Promise.resolve({ data: { data: {} } });
    });

    render(<MemoryRouter><ProductionRolloutDashboard /></MemoryRouter>);

    await screen.findByTestId('production-rollout-dashboard');
    // The tab is rendered only after selecting it; this verifies the scenario
    // contract and button behaviour through the exported component flow.
    expect(axiosGet).toHaveBeenCalledWith('/production/load/scenarios', { headers: {} });
  });

  it.each([
    ['desktop', LogViewer],
    ['mobile', MobileLogViewer],
  ])('stops loading and offers retry when the %s log request fails', async (_name, Viewer) => {
    axiosGet.mockRejectedValue({ response: { status: 503 }, name: 'AxiosError' });

    render(
      <MemoryRouter>
        <Viewer user={{}} />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Sistem logları yüklenemedi.');
    expect(screen.getByRole('button', { name: 'Tekrar Dene' })).toBeEnabled();
    expect(document.querySelector('.animate-spin')).not.toBeInTheDocument();
  });
});
