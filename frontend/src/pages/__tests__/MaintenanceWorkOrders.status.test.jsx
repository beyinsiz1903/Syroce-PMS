import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MaintenanceWorkOrders from '@/pages/MaintenanceWorkOrders';

const { get, patch, toast } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('axios', () => ({ default: { get, patch } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/hooks/useMediaCapture', () => ({
  default: () => ({ uploadMedia: vi.fn(), uploading: false }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key, fallback) => (typeof fallback === 'string' ? fallback : _key),
  }),
}));

afterEach(() => cleanup());

describe('MaintenanceWorkOrders status actions', () => {
  beforeEach(() => {
    get.mockReset();
    patch.mockReset();
    toast.error.mockReset();
    toast.success.mockReset();
    get.mockResolvedValue({
      data: {
        items: [{
          id: 'work-order-test',
          room_number: 'QT2ED0',
          issue_type: 'housekeeping_damage',
          description: 'TST maintenance',
          source: 'housekeeping',
          reported_by_role: 'super_admin',
          priority: 'normal',
          status: 'open',
        }],
      },
    });
  });

  it('sends Start using the query-parameter contract and verifies the durable update', async () => {
    patch.mockResolvedValue({ data: { updated: true } });
    render(<MaintenanceWorkOrders />);

    fireEvent.click(await screen.findByRole('button', { name: 'Start' }));

    await waitFor(() => expect(patch).toHaveBeenCalledWith(
      '/maintenance/work-orders/work-order-test',
      null,
      { params: { status: 'in_progress' } },
    ));
    expect(toast.success).toHaveBeenCalledWith('İş emri başlatıldı');
  });

  it('does not report success when the backend did not modify the work order', async () => {
    patch.mockResolvedValue({ data: { updated: false } });
    render(<MaintenanceWorkOrders />);

    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('İş emri durumu güncellenemedi'));
    expect(toast.success).not.toHaveBeenCalled();
  });
});
