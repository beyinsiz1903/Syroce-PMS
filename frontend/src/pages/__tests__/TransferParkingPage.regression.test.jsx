import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import TransferParkingPage from '@/pages/TransferParkingPage';

const { get, deleteRequest, confirmDialog } = vi.hoisted(() => ({
  get: vi.fn(),
  deleteRequest: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({
  default: { get, delete: deleteRequest },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/context/EntitlementContext', () => ({
  useEntitlements: () => ({
    getLimit: () => 10,
    hasFeature: () => false,
  }),
}));

afterEach(() => cleanup());

describe('Transfer and parking regressions', () => {
  beforeEach(() => {
    get.mockReset();
    deleteRequest.mockReset();
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
    deleteRequest.mockResolvedValue({ data: { ok: true } });
    get.mockImplementation((url) => {
      if (url === '/transfer-parking/resources') return Promise.resolve({ data: { resources: [] } });
      if (url === '/transfer-parking/bookings') return Promise.resolve({ data: { bookings: [{
        id: 'transport-1', kind: 'transfer_vehicle', resource_name: 'QA Transfer',
        room_number: '998', guest_name: 'QA', total: 500, status: 'reserved',
        folio_charged: false, schedule: { pickup_at: '2026-11-11T00:00:00Z' },
      }] } });
      if (url === '/transfer-parking/late-charges') return Promise.resolve({ data: { late_charges: [] } });
      return Promise.resolve({ data: {} });
    });
  });

  it('refreshes bookings and late charges after cancellation', async () => {
    render(<MemoryRouter><TransferParkingPage /></MemoryRouter>);

    await screen.findByText('QA Transfer');
    const row = screen.getByText('QA Transfer').closest('tr');
    fireEvent.click(row.querySelector('button'));

    await waitFor(() => expect(deleteRequest).toHaveBeenCalledWith('/transfer-parking/bookings/transport-1'));
    await waitFor(() => {
      expect(get.mock.calls.filter(([url]) => url === '/transfer-parking/bookings')).toHaveLength(2);
      expect(get.mock.calls.filter(([url]) => url === '/transfer-parking/late-charges')).toHaveLength(2);
    });
  });
});
