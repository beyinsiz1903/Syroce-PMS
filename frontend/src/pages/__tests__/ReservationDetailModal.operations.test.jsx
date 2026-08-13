import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import ReservationDetailModal from '@/pages/ReservationDetailModal';

const { get, post, confirmDialog, axiosMock } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return {
    get,
    post,
    confirmDialog: vi.fn(),
    axiosMock: Object.assign(vi.fn(), {
      get,
      post,
      put: vi.fn(),
      defaults: { headers: { common: {} } },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    }),
  };
});
vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key, fallback) => fallback || _key }),
}));

const detail = {
  booking: {
    id: 'booking-test', status: 'confirmed', room_id: 'room-test', room_number: '106',
    guest_name: 'TEST GUEST', check_in: '2026-08-13', check_out: '2026-08-14',
    created_at: '2026-08-13T12:00:00Z', channel: 'direct', adults: 1, children: 0,
  },
  guest: { id: 'guest-test', name: 'TEST GUEST' },
  room: { id: 'room-test', room_number: '106', room_type: 'Standard', status: 'available' },
  folios: [], charges: [], payments: [], extra_charges: [], notes: [], history: [],
  room_moves: [], daily_rates: [], guests: [], communication_logs: [], deposits: [],
  summary: { balance: 0, total_amount: 0, total_payments: 0 },
};

describe('ReservationDetailModal operation URLs', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: detail });
    post.mockReset();
    post.mockResolvedValue({ data: { success: true } });
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
  });

  afterEach(() => cleanup());

  it('sends no-show to the single /api-prefixed axios base path', async () => {
    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: 'No-Show' }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledOnce());
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-test/mark-noshow',
      {},
    ));
    expect(post).not.toHaveBeenCalledWith(expect.stringContaining('/api/api/'), expect.anything());
  });
});
