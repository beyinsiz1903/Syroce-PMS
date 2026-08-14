import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet, axiosPost, confirmDialog, toastInfo, toastSuccess, toastWarning } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPost: vi.fn(),
  confirmDialog: vi.fn(),
  toastInfo: vi.fn(),
  toastSuccess: vi.fn(),
  toastWarning: vi.fn(),
}));

vi.mock('axios', () => ({
  default: { get: axiosGet, post: axiosPost },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: toastInfo,
    success: toastSuccess,
    warning: toastWarning,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }),
}));

import ARIPushDashboard from '@/pages/ARIPushDashboard';

describe('ARI provider test harness disclosure', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
    confirmDialog.mockReset();
    toastInfo.mockReset();
    toastSuccess.mockReset();
    toastWarning.mockReset();
    confirmDialog.mockResolvedValue(true);
    axiosGet.mockImplementation((url) => {
      if (url.includes('/change-sets')) return Promise.resolve({ data: { change_sets: [] } });
      if (url.includes('/engine-stats')) return Promise.resolve({ data: { registered_adapters: [] } });
      if (url.includes('/drift/mode')) return Promise.resolve({ data: { mode: 'normal', interval: 120 } });
      return Promise.resolve({ data: {} });
    });
    axiosPost.mockResolvedValue({
      data: {
        provider: 'hotelrunner',
        execution_mode: 'dry_run',
        provider_verified: false,
        provider_write_count: 0,
        results: [{ step: 'connect', success: true, detail: 'DRY-RUN: no client configured', duration_ms: 0 }],
        summary: { total: 1, passed: 1, failed: 0, offline_checks_passed: true },
      },
    });
  });

  afterEach(() => cleanup());

  it('labels dry-run results without claiming provider success', async () => {
    render(<ARIPushDashboard user={{ tenant_id: 'tenant-1', hotel_id: 'hotel-1' }} tenant={{}} />);

    fireEvent.click(screen.getByRole('tab', { name: 'Test Paneli' }));
    fireEvent.click(screen.getByTestId('run-test-hotelrunner'));

    await waitFor(() => expect(screen.getByTestId('dry-run-warning-hotelrunner')).toBeInTheDocument());
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Offline kontrol paketi',
    }));
    expect(toastInfo).toHaveBeenCalledWith(expect.stringContaining('provider doğrulanmadı'));
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
