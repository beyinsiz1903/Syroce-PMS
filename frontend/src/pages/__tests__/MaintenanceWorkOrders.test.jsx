import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';

import MaintenanceWorkOrders from '../MaintenanceWorkOrders';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const OPEN_WORK_ORDER = {
  id: 'work-order-1',
  room_number: '101',
  issue_type: 'electrical',
  description: 'Test issue',
  source: 'housekeeping',
  reported_by_role: 'super_admin',
  priority: 'high',
  status: 'open',
  created_at: '2026-08-15T10:00:00Z',
};

describe('MaintenanceWorkOrders status actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { items: [OPEN_WORK_ORDER] } });
  });

  it('sends the status using the backend query contract', async () => {
    axios.patch.mockResolvedValue({ data: { updated: true } });
    render(<MaintenanceWorkOrders />);

    fireEvent.click(await screen.findByRole('button', { name: 'Start' }));

    await waitFor(() => {
      expect(axios.patch).toHaveBeenCalledWith(
        '/maintenance/work-orders/work-order-1',
        null,
        { params: { status: 'in_progress' } },
      );
    });
    expect(toast.success).toHaveBeenCalledWith('İş emri başlatıldı');
  });

  it('reports a controlled failure when the backend changes nothing', async () => {
    axios.patch.mockResolvedValue({ data: { updated: false } });
    render(<MaintenanceWorkOrders />);

    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('İş emri durumu güncellenemedi');
    });
    expect(toast.success).not.toHaveBeenCalled();
  });
});
